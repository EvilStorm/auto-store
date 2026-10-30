"""④ 원가·마진율·후보 점수. 설계서 6장의 식을 그대로 옮겼다."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.adapters.exchange_rate import Rates
from app.config import settings
from app.pipeline.extract import Normalized, RawDetail
from app.pipeline.match import MatchResult


class CostBreakdown(BaseModel):
    currency: str
    rate_krw: float
    unit_price_src: float
    moq: int
    purchase_krw: int
    local_shipping_krw: int
    proxy_fee_krw: int
    forwarder_krw: int
    customs_krw: int
    naver_fee_krw: int
    payment_fee_krw: int
    fx_buffer_krw: int
    total_cost_krw: int
    taxable_usd: float
    weight_g: float
    flags: list[str] = Field(default_factory=list)


class Economics(BaseModel):
    cost: CostBreakdown
    domestic_price_krw: Optional[int] = None
    margin_rate: Optional[float] = None
    suggested_price_krw: Optional[int] = None  # 총원가 ÷ (1 − 목표 마진율), 100원 올림
    score: Optional[float] = None
    score_parts: dict = Field(default_factory=dict)


def _forwarder_fee(weight_g: float) -> int:
    if weight_g <= 0:
        return 0
    kg = weight_g / 1000.0
    for limit, won in settings.forwarder_rate_table():
        if kg <= limit:
            return won
    last_limit, last_won = settings.forwarder_rate_table()[-1]
    # 표 밖은 마지막 구간 요금에 0.5kg 당 1,500원 가산
    extra = int((kg - last_limit) / 0.5 + 0.999) * 1500
    return last_won + extra


def _unit_price_at_moq(raw: RawDetail) -> tuple[float, int]:
    moq = max(1, raw.moq or 1)
    tiers = sorted(raw.price_tiers, key=lambda t: t.min_qty)
    if not tiers:
        return 0.0, moq
    price = tiers[0].unit_price
    for t in tiers:
        if t.min_qty <= moq:
            price = t.unit_price
    return float(price), moq


def compute(raw: RawDetail, norm: Normalized, match: MatchResult, rates: Rates) -> Economics:
    if raw.currency == "KRW":
        cur, rate = "KRW", 1.0
    else:
        cur = raw.currency if raw.currency in rates.rates else "CNY"
        rate = rates.rates[cur]
    usd = rates.rates["USD"]
    unit, moq = _unit_price_at_moq(raw)
    flags: list[str] = []

    purchase = unit * moq * rate
    # 현지 배송비 기본값은 소스 국가 기준. 페이지가 원화로 표시돼도 중국 사이트면 CNY 기본값을 환산해 쓴다.
    if cur == "JPY":
        local_ship = 800 * rate
    elif cur == "USD":
        local_ship = 3.0 * rate
    else:
        local_ship = settings.local_shipping_cny * rates.rates["CNY"]
    proxy = (purchase + local_ship) * settings.proxy_fee_rate
    weight = float(raw.weight_g or 0)
    if weight <= 0:
        flags.append("weight_unknown")
    forwarder = _forwarder_fee(weight)
    taxable_usd = (purchase + local_ship) / usd if usd else 0
    customs = 0.0
    if taxable_usd > settings.customs_limit_usd:
        customs = (purchase + local_ship) * (settings.customs_duty_rate + settings.vat_rate * (1 + settings.customs_duty_rate))
        flags.append("over_customs_limit")
    elif taxable_usd > settings.customs_warn_usd:
        flags.append("near_customs_limit")
    fx_buffer = purchase * settings.fx_buffer_rate

    domestic = match.domestic_price_krw
    naver_fee = (domestic or 0) * settings.naver_fee_rate
    payment_fee = (domestic or 0) * settings.payment_fee_rate
    if rates.source in ("last_known", "fallback_constant"):
        flags.append("rate_stale")
    if norm.requirement_status == "required":
        flags.append("requirement_needed")
    if norm.brand_detected:
        flags.append("brand_detected")
    if match.basis_match_type == "similar":
        flags.append("price_is_reference")

    total = purchase + local_ship + proxy + forwarder + customs + naver_fee + payment_fee + fx_buffer
    cost = CostBreakdown(
        currency=cur,
        rate_krw=round(rate, 2),
        unit_price_src=unit,
        moq=moq,
        purchase_krw=round(purchase),
        local_shipping_krw=round(local_ship),
        proxy_fee_krw=round(proxy),
        forwarder_krw=forwarder,
        customs_krw=round(customs),
        naver_fee_krw=round(naver_fee),
        payment_fee_krw=round(payment_fee),
        fx_buffer_krw=round(fx_buffer),
        total_cost_krw=round(total),
        taxable_usd=round(taxable_usd, 1),
        weight_g=weight,
        flags=flags,
    )
    econ = Economics(cost=cost, domestic_price_krw=domestic)

    # 수수료를 뺀 "상품 원가"로 판매가 제안 (수수료는 판매가에 비례하므로 역산)
    base_cost = total - naver_fee - payment_fee
    fee_r = settings.naver_fee_rate + settings.payment_fee_rate
    denom = 1 - settings.target_margin_rate - fee_r
    if denom > 0 and base_cost > 0:
        econ.suggested_price_krw = int(-(-base_cost / denom // 100) * 100)

    if domestic:
        econ.margin_rate = round((domestic - total) / domestic, 4)
        parts = {"margin": round(econ.margin_rate * 100, 1)}
        comp = 0
        if match.exact_count <= 2:
            comp = 15
        elif match.exact_count <= 5:
            comp = 5
        if match.same_image_sellers is not None and match.same_image_sellers >= settings.same_image_seller_cap:
            comp -= 20
        # 가격비교 카탈로그 판매처가 많으면 이미 포화된 상품 (100곳 이상 감점)
        if match.max_seller_count is not None and match.max_seller_count >= 100:
            comp -= 10
        parts["competition"] = comp
        demand = 0
        if match.demand_trend_pct is not None:
            demand = 10 if match.demand_trend_pct > 5 else (-10 if match.demand_trend_pct < -5 else 0)
        parts["demand"] = demand
        risk = 0
        if "weight_unknown" in flags:
            risk -= 5
        if "near_customs_limit" in flags or "over_customs_limit" in flags:
            risk -= 5
        if "requirement_needed" in flags:
            risk -= 10
        parts["risk"] = risk
        econ.score = round(parts["margin"] + comp + demand + risk, 1)
        econ.score_parts = parts
    return econ
