"""후보 카드 텍스트. 텔레그램과 CLI 가 같은 포맷을 쓴다."""
from __future__ import annotations

from app.pipeline.cost import Economics
from app.pipeline.extract import Normalized, RawDetail
from app.pipeline.match import MatchResult

FLAG_KO = {
    "weight_unknown": "무게 미확인 → 배대지 요금 미반영",
    "near_customs_limit": "과세가격 130달러 초과 (경계)",
    "over_customs_limit": "150달러 초과 → 관부가세 반영",
    "rate_stale": "환율이 오래됨",
    "requirement_needed": "요건 필요 (KC 등)",
    "brand_detected": "브랜드 로고/상표 감지",
    "price_is_reference": "국내가는 유사 상품 기준(참고치)",
}


def _won(v) -> str:
    return "-" if v is None else f"{int(v):,}원"


def render_card(url: str, host: str, raw: RawDetail, norm: Normalized, match: MatchResult, econ: Economics, *, llm_cost_krw: float = 0.0) -> str:
    c = econ.cost
    lines = []
    status = "제외" if norm.requirement_status == "excluded" or norm.brand_detected else ("요건 필요" if norm.requirement_status == "required" else "통과")
    lines.append(f"[{host}] {norm.title_ko}")
    lines.append(f"원문  {raw.title_raw[:60]}")
    lines.append(f"소스가  {c.currency} {c.unit_price_src:g} × 최소 {c.moq}개 = {_won(c.purchase_krw)} (환율 {c.rate_krw})")
    if match.skipped_reason:
        lines.append(f"국내 비교가  (생략: {match.skipped_reason})")
    else:
        basis = "정확" if match.basis_match_type == "exact" else "유사·참고치"
        lines.append(f"국내 비교가  {_won(match.domestic_price_krw)} ({basis} · {match.price_basis} · 상위 {match.exact_count + match.similar_count}건)")
    lines.append(
        f"총원가  {_won(c.total_cost_krw)}  →  마진율 {('%.0f%%' % (econ.margin_rate * 100)) if econ.margin_rate is not None else '-'}"
        f"  ·  제안 판매가 {_won(econ.suggested_price_krw)}"
    )
    lines.append(
        f"원가 내역  구매 {_won(c.purchase_krw)} · 현지배송 {_won(c.local_shipping_krw)} · 대리구매 {_won(c.proxy_fee_krw)} · 배대지 {_won(c.forwarder_krw)}"
        f" · 관부가세 {_won(c.customs_krw)} · 수수료 {_won(c.naver_fee_krw + c.payment_fee_krw)} · 환차손완충 {_won(c.fx_buffer_krw)}"
    )
    if not match.skipped_reason:
        demand = "미연결" if match.demand_trend_pct is None else f"{match.demand_trend_pct:+.0f}%"
        same = "미연결" if match.same_image_sellers is None else f"{match.same_image_sellers}곳"
        lines.append(f"경쟁  정확 {match.exact_count} · 유사 {match.similar_count} · 결과 {match.total_results:,}건 · 동일 이미지 판매자 {same}")
        lines.append(f"수요  {demand}  ·  리뷰  미연결")
        if match.reason:
            lines.append(f"근거  {match.reason}")
        if match.naver_category:
            lines.append(f"네이버 카테고리 추천  {match.naver_category}")
    lines.append(f"점수  {econ.score if econ.score is not None else '-'}  ·  요건 {status} ({norm.requirement_reason})")
    lines.append(f"재질  {norm.material_code} · 품목 {norm.item_type} · 무게 {c.weight_g:g}g")
    if norm.brand_detected:
        lines.append(f"브랜드  감지됨: {norm.brand_reason}")
    if c.flags:
        lines.append("주의  " + " / ".join(FLAG_KO.get(f, f) for f in c.flags))
    if match.exact:
        lines.append("정확 매칭  " + " | ".join(f"{r['mall']} {r['price']:,}" for r in match.exact[:3]))
    lines.append(f"검색어  {', '.join(match.queries)}")
    lines.append(f"링크  {url}")
    lines.append(f"(LLM 추정 비용 {llm_cost_krw:,.0f}원)")
    return "\n".join(lines)
