from app.adapters.exchange_rate import Rates
from app.adapters.telegram import callback_data, parse_callback
from app.pipeline import notify, scoring

RATES = Rates({"CNY": 200.0, "JPY": 9.0, "USD": 1400.0}, "open_er_api", "2026-11-01T00:00:00")


def item(**over):
    base = {"id": 1, "source_id": "1688", "source_item_id": "6912", "currency": "CNY", "moq": 2, "url": "https://detail.1688.com/offer/6912.html",
            "title_raw": "不锈钢保温杯 500ml", "price_tiers_json": [{"min_qty": 2, "unit_price": 18.5}, {"min_qty": 50, "unit_price": 16.0}]}
    base.update(over)
    return base


def signals(**over):
    base = {"exact_count": 3, "similar_count": 7, "total_results": 20, "same_image_sellers": 2, "review_top": 210, "wish_top": 40,
            "seller_count_max": 41, "price_mean": 24900, "price_median": 23900, "price_min": 19900, "basis_type": "exact"}
    base.update(over)
    return base


def test_unit_price_at_moq_picks_tier():
    assert scoring.unit_price_at_moq([{"min_qty": 2, "unit_price": 18.5}, {"min_qty": 50, "unit_price": 16.0}], 2) == (18.5, 2)
    assert scoring.unit_price_at_moq([{"min_qty": 2, "unit_price": 18.5}, {"min_qty": 50, "unit_price": 16.0}], 100) == (16.0, 100)
    assert scoring.unit_price_at_moq([], 0) == (0.0, 1)


def test_forwarder_fee_table_and_overflow():
    table = [(0.5, 6000), (1.0, 7500)]
    assert scoring.forwarder_fee(0, table) == 0
    assert scoring.forwarder_fee(300, table) == 6000
    assert scoring.forwarder_fee(1000, table) == 7500
    assert scoring.forwarder_fee(2000, table) == 7500 + 2 * 1500


def test_compute_economics_margin_and_score():
    e = scoring.compute_economics(item(), signals(), RATES, weight_g=350)
    assert e.purchase_krw == 18.5 * 2 * 200          # 7,400
    assert e.local_shipping_krw == 8 * 200            # 기본 CNY 8
    assert e.forwarder_krw == 6000                    # 350g → 0.5kg 구간
    assert e.customs_krw == 0 and "weight_unknown" not in e.flags
    assert e.domestic_price_krw == 24900              # price_basis mean
    assert e.margin_rate is not None and 0 < e.margin_rate < 1
    assert e.suggested_price_krw % 100 == 0
    # 경쟁 +5 (정확 3) · 수요 +5 (리뷰 210) · 리스크 0
    assert e.score_parts["competition"] == 5 and e.score_parts["demand"] == 5 and e.score_parts["risk"] == 0
    assert e.score == round(e.score_parts["margin"] + 10, 1)


def test_flags_and_penalties():
    e = scoring.compute_economics(item(price_tiers_json=[{"min_qty": 1, "unit_price": 600.0}], moq=2), signals(same_image_sellers=7, seller_count_max=150, basis_type="similar"),
                                  RATES, weight_g=0, requirement_status="required")
    assert "over_customs_limit" in e.flags and e.customs_krw > 0      # 600×2×200 = 240,000원 ≈ 171 USD
    assert "weight_unknown" in e.flags and "requirement_needed" in e.flags and "price_is_reference" in e.flags
    assert e.score_parts["competition"] == 5 - 20 - 10
    assert e.score_parts["risk"] == -5 - 5 - 10


def test_no_signals_means_no_margin():
    e = scoring.compute_economics(item(), None, RATES, weight_g=0)
    assert e.margin_rate is None and e.score is None and e.suggested_price_krw is not None


def test_shipping_profile_overrides_defaults():
    sp = {"currency": "CNY", "local_shipping_default": 12, "proxy_fee_rate": 0.08, "rate_table_json": [{"kg_max": 1.0, "won": 9000}]}
    e = scoring.compute_economics(item(), signals(), RATES, weight_g=400, shipping_profile=sp)
    assert e.local_shipping_krw == 12 * 200 and e.forwarder_krw == 9000
    assert e.proxy_fee_krw == round((e.purchase_krw + e.local_shipping_krw) * 0.08)


def test_render_card_and_callbacks():
    e = scoring.compute_economics(item(), signals(), RATES, weight_g=350)
    cand = {"id": 7, "cost_breakdown_json": e.breakdown(), "margin_rate": e.margin_rate, "domestic_price_krw": e.domestic_price_krw,
            "suggested_price_krw": e.suggested_price_krw, "score": e.score, "score_parts_json": e.score_parts, "flags": e.flags}
    norm = {"title_clean": "不锈钢保温杯 500ml", "search_queries": ["텀블러 500ml", "보온병 스테인리스"]}
    text = notify.render_card(item(), norm, signals(), cand, matches=[{"title": "킨토 텀블러 500ml", "price": 21500, "reason": "이미지 유사도 0.71 · 용량 일치"}],
                              logo={"logo_detected": False})
    assert "마진율" in text and "텀블러 500ml" in text and "로고 확인  없음" in text and "킨토" in text
    assert parse_callback(callback_data("c", 7, "approve")) == ("c", 7, "approve")
    assert parse_callback("garbage") is None
