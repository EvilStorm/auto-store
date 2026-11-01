from datetime import date

from app.pipeline import monitor


def test_snapshot_and_diff_price_moq_options():
    before = monitor.snapshot([{"min_qty": 1, "unit_price": 8.9}], 1, [{"name_raw": "A", "sold_out": False}, {"name_raw": "B", "sold_out": False}], False)
    after = monitor.snapshot([{"min_qty": 2, "unit_price": 10.5}], 2, [{"name_raw": "A", "sold_out": True}, {"name_raw": "B", "sold_out": False}], False)
    ev = monitor.diff(before, after, price_threshold=0.05)
    kinds = [e["kind"] for e in ev]
    assert kinds == ["price", "moq", "option_soldout"]
    assert ev[0]["after"]["change_pct"] == 18.0 and ev[2]["after"]["newly"] == ["A"]


def test_diff_below_threshold_is_silent():
    b = monitor.snapshot([{"min_qty": 1, "unit_price": 10.0}], 1, [], False)
    a = monitor.snapshot([{"min_qty": 1, "unit_price": 10.3}], 1, [], False)
    assert monitor.diff(b, a, price_threshold=0.05) == []


def test_diff_soldout_removed_restored():
    base = monitor.snapshot([{"min_qty": 1, "unit_price": 10.0}], 1, [], False)
    assert [e["kind"] for e in monitor.diff(base, {**base, "sold_out": True})] == ["soldout"]
    assert [e["kind"] for e in monitor.diff(base, {**base, "page_missing": True})] == ["removed"]
    assert [e["kind"] for e in monitor.diff({**base, "sold_out": True}, base)] == ["restored"]
    assert [e["kind"] for e in monitor.diff({**base, "page_missing": True}, base)] == ["restored"]


def test_eta():
    assert monitor.eta(date(2026, 11, 1), 12) == date(2026, 11, 13)
    assert monitor.eta(None, 12) is None


def test_event_text():
    ev = {"kind": "price", "before_json": {"unit_price": 8.9}, "after_json": {"unit_price": 10.5, "change_pct": 18.0}, "recalculated_margin": 0.12, "suggested_price_krw": 17900}
    t = monitor.event_text(ev, {"sale_price_krw": 15400, "store_product_no": "1234"}, {"title_raw": "보온杯", "url": "https://x"})
    assert "¥8.9 → ¥10.5 (+18%)" in t and "마진율 12%" in t and "17,900원" in t and "#1234" in t
