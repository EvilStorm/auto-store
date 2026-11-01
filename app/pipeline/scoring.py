"""④ 개인 원가 · 마진율 · 후보 점수 → candidates (DESIGN.md 6-④). LLM 0회.

  python -m app.pipeline.scoring            # 시장 신호가 있는 상품 중 오늘 후보 행이 없는 것 전부
  python -m app.pipeline.scoring --item 123

공용 market_signals(사실) × 내 설정(환율은 공용, 배송 프로필 · 수수료 · 마진 기준은 개인) → 개인 candidates.
cost.py 의 식을 그대로 승계했고, compute_economics() 는 DB 없이 테스트할 수 있는 순수 함수다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app import repo
from app.adapters.exchange_rate import Rates
from app.config import settings


@dataclass
class Economics:
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
    domestic_price_krw: int | None
    margin_rate: float | None
    suggested_price_krw: int | None
    score: float | None
    score_parts: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def breakdown(self) -> dict:
        return {k: getattr(self, k) for k in ("currency", "rate_krw", "unit_price_src", "moq", "purchase_krw", "local_shipping_krw",
                                               "proxy_fee_krw", "forwarder_krw", "customs_krw", "naver_fee_krw", "payment_fee_krw",
                                               "fx_buffer_krw", "total_cost_krw", "taxable_usd", "weight_g")}


def forwarder_fee(weight_g: float, table: list[tuple[float, int]]) -> int:
    if weight_g <= 0 or not table:
        return 0
    kg = weight_g / 1000.0
    for limit, won in table:
        if kg <= limit:
            return won
    last_limit, last_won = table[-1]
    return last_won + int((kg - last_limit) / 0.5 + 0.999) * 1500   # 표 밖은 0.5kg 당 1,500원 가산


def unit_price_at_moq(price_tiers: list[dict], moq: int) -> tuple[float, int]:
    moq = max(1, int(moq or 1))
    tiers = sorted((t for t in (price_tiers or []) if t.get("unit_price") is not None), key=lambda t: t.get("min_qty", 1))
    if not tiers:
        return 0.0, moq
    price = float(tiers[0]["unit_price"])
    for t in tiers:
        if int(t.get("min_qty", 1)) <= moq:
            price = float(t["unit_price"])
    return price, moq


def compute_economics(item: dict, signals: dict | None, rates: Rates, *, weight_g: float = 0.0, requirement_status: str = "pass",
                      brand_hit: bool = False, local_shipping_src: float | None = None, shipping_profile: dict | None = None,
                      weight_source: str = "listed") -> Economics:
    """item: source_items 행(price_tiers_json · moq · currency). signals: market_signals 행 (없으면 마진 계산 생략)."""
    s = settings
    cur = item.get("currency") or "CNY"
    if cur == "KRW":
        rate = 1.0
    else:
        cur = cur if cur in rates.rates else "CNY"
        rate = rates.rates[cur]
    usd = rates.rates.get("USD") or 1400.0
    unit, moq = unit_price_at_moq(item.get("price_tiers_json") or [], item.get("moq") or 1)
    flags: list[str] = []

    purchase = unit * moq * rate
    sp = shipping_profile or {}
    proxy_rate = float(sp.get("proxy_fee_rate", s.proxy_fee_rate))
    if local_shipping_src is not None:
        local_ship = local_shipping_src * rate
    elif sp.get("local_shipping_default") is not None:
        local_ship = float(sp["local_shipping_default"]) * (rates.rates.get(sp.get("currency", cur), rate))
    elif cur == "JPY":
        local_ship = 800 * rate
    elif cur == "USD":
        local_ship = 3.0 * rate
    else:
        local_ship = s.local_shipping_cny * rates.rates["CNY"]
    proxy = (purchase + local_ship) * proxy_rate
    if weight_g <= 0:
        flags.append("weight_unknown")
    table = [(float(r["kg_max"]), int(r["won"])) for r in sp["rate_table_json"]] if sp.get("rate_table_json") else s.forwarder_rate_table()
    forwarder = forwarder_fee(weight_g, table)
    taxable_usd = (purchase + local_ship) / usd if usd else 0
    customs = 0.0
    if taxable_usd > s.customs_limit_usd:
        customs = (purchase + local_ship) * (s.customs_duty_rate + s.vat_rate * (1 + s.customs_duty_rate))
        flags.append("over_customs_limit")
    elif taxable_usd > s.customs_warn_usd:
        flags.append("near_customs_limit")
    fx_buffer = purchase * s.fx_buffer_rate

    domestic = None
    if signals:
        domestic = signals.get({"mean": "price_mean", "median": "price_median", "min": "price_min"}.get(s.price_basis, "price_mean"))
        if signals.get("basis_type") == "similar":
            flags.append("price_is_reference")
        basis_n = int(signals.get("exact_count") or 0) or int(signals.get("similar_count") or 0)
        if domestic and basis_n < 3:
            flags.append("few_matches")          # 비교가가 1~2건에 기댐 → 리스크 감점
        if not domestic:
            flags.append("no_domestic_price")    # 네이버에서 같은/비슷한 상품을 못 찾음 → 마진 계산 불가
    if weight_g > 0 and weight_source == "category_default":
        flags.append("weight_estimated")
    naver_fee = (domestic or 0) * s.naver_fee_rate
    payment_fee = (domestic or 0) * s.payment_fee_rate
    if rates.source in ("last_known", "fallback_constant"):
        flags.append("rate_stale")
    if requirement_status == "required":
        flags.append("requirement_needed")
    elif requirement_status == "unknown":
        flags.append("requirement_unknown")
    if brand_hit:
        flags.append("brand_detected")

    total = purchase + local_ship + proxy + forwarder + customs + naver_fee + payment_fee + fx_buffer
    base_cost = total - naver_fee - payment_fee
    fee_r = s.naver_fee_rate + s.payment_fee_rate
    denom = 1 - s.target_margin_rate - fee_r
    suggested = int(-(-base_cost / denom // 100) * 100) if (denom > 0 and base_cost > 0) else None

    margin = score = None
    parts: dict = {}
    if domestic:
        margin = round((domestic - total) / domestic, 4)
        parts["margin"] = round(margin * 100, 1)
        exact = int(signals.get("exact_count") or 0)
        comp = 15 if exact <= 2 else 5 if exact <= 5 else 0
        same_img = signals.get("same_image_sellers")
        if same_img is not None and same_img >= s.same_image_seller_cap:
            comp -= 20
        if (signals.get("seller_count_max") or 0) >= 100:
            comp -= 10
        parts["competition"] = comp
        # 수요 대리값 (데이터랩 붙으면 추이 ±10 으로 교체)
        demand = 0
        trend = signals.get("demand_trend_pct")
        if trend is not None:
            demand = 10 if trend > 5 else (-10 if trend < -5 else 0)
        else:
            rt = signals.get("review_top") or 0
            demand = 10 if rt >= 1000 else 5 if rt >= 100 else 0
            if (signals.get("wish_top") or 0) >= 500:
                demand += 5
        parts["demand"] = demand
        risk = 0
        if "weight_unknown" in flags:
            risk -= 5
        if "near_customs_limit" in flags or "over_customs_limit" in flags:
            risk -= 5
        if "requirement_needed" in flags or "requirement_unknown" in flags:
            risk -= 10
        if "few_matches" in flags:
            risk -= 5
        parts["risk"] = risk
        score = round(parts["margin"] + comp + demand + risk, 1)

    return Economics(
        currency=cur, rate_krw=round(rate, 2), unit_price_src=unit, moq=moq, purchase_krw=round(purchase), local_shipping_krw=round(local_ship),
        proxy_fee_krw=round(proxy), forwarder_krw=forwarder, customs_krw=round(customs), naver_fee_krw=round(naver_fee), payment_fee_krw=round(payment_fee),
        fx_buffer_krw=round(fx_buffer), total_cost_krw=round(total), taxable_usd=round(taxable_usd, 1), weight_g=weight_g,
        domestic_price_krw=domestic, margin_rate=margin, suggested_price_krw=suggested, score=score, score_parts=parts, flags=flags,
    )


# ───────────────────────── DB 가 있는 부분 ─────────────────────────
def _excluded_by_me(norm: dict, item: dict, rules: list[dict], rejections: list[dict], listed_item_ids: set[int]) -> str | None:
    if item["id"] in listed_item_ids:
        return "already_listed"
    for rj in rejections:
        if rj.get("source_id") == item["source_id"] and rj.get("source_item_id") == item["source_item_id"]:
            return "rejected_before"
    for r in rules:
        if not r.get("enabled", True):
            continue
        if r["kind"] == "material" and norm.get("material_code") == r["code_or_term"]:
            return f"my_rule:material:{r['code_or_term']}"
        if r["kind"] == "item_type" and norm.get("item_type") == r["code_or_term"]:
            return f"my_rule:item_type:{r['code_or_term']}"
        if r["kind"] == "keyword" and r["code_or_term"].lower() in (item.get("title_raw") or "").lower():
            return f"my_rule:keyword:{r['code_or_term']}"
    return None


def run(c, user_id: str, *, only_item: int | None = None, run_date: date | None = None, origin: str = "batch") -> dict:
    from app.adapters.exchange_rate import get_rates
    from app.taxonomy import dictionary

    today = run_date or date.today()
    rates = get_rates(client=c)
    d = dictionary.from_db(c)
    rules = c.table("user_exclusion_rules").select("*").execute().data
    rejections = c.table("rejections").select("source_id, source_item_id, image_phash").gte("until", datetime.now(timezone.utc).isoformat()).execute().data
    listed = {r["source_item_id"] for r in c.table("candidates").select("source_item_id").in_("status", ["listed", "suspended", "approved_1", "approved_2", "packaged"]).execute().data}
    profiles = c.table("shipping_profiles").select("*").execute().data
    us = {r["source_id"]: r for r in c.table("user_sources").select("source_id, shipping_profile_id").execute().data}
    prof_by_id = {p["id"]: p for p in profiles}

    q = c.table("market_signals").select("*")
    if only_item:
        q = q.eq("source_item_id", only_item)
    signals = q.execute().data
    ids = [s["source_item_id"] for s in signals]
    if not ids:
        return {"scored": 0}
    items = {i["id"]: i for i in c.table("source_items").select("*").in_("id", ids).execute().data}
    norms = {n["source_item_id"]: n for n in c.table("source_items_normalized").select("*").in_("source_item_id", ids).execute().data}
    existing = {r["source_item_id"]: r for r in c.table("candidates").select("id, source_item_id, status").eq("run_date", today.isoformat()).in_("source_item_id", ids).execute().data}
    details = {r["source_item_id"]: r for r in c.table("source_item_details").select("source_item_id, package_weight_g").in_("source_item_id", ids).execute().data}

    out = {"scored": 0, "candidate": 0, "below_margin": 0, "excluded": 0, "skipped": 0}
    rows = []
    for sig in signals:
        sid = sig["source_item_id"]
        item, norm = items.get(sid), norms.get(sid)
        if not item or not norm or norm.get("excluded_reason"):
            out["skipped"] += 1
            continue
        ex = existing.get(sid)
        if ex and ex["status"] not in ("candidate", "below_margin"):
            out["skipped"] += 1   # 이미 결정된 후보는 다시 점수 내지 않음
            continue
        if _excluded_by_me(norm, item, rules, rejections, listed):
            out["excluded"] += 1
            continue
        cat = d.categories.get(norm.get("canonical_category_id") or "")
        detail_w = (details.get(sid) or {}).get("package_weight_g")
        weight = float(detail_w or (cat.default_weight_g if cat else 0) or 0)
        weight_source = "detail" if detail_w else ("category_default" if weight > 0 else "unknown")
        status, _ = d.requirement(norm.get("item_type") or "general")
        sp = prof_by_id.get((us.get(item["source_id"]) or {}).get("shipping_profile_id"))
        econ = compute_economics(item, sig, rates, weight_g=weight, requirement_status=status, brand_hit=bool(norm.get("brand_text_hit")),
                                 shipping_profile=sp, weight_source=weight_source)
        st = "candidate" if (econ.margin_rate is not None and econ.margin_rate >= settings.margin_threshold) else "below_margin"
        out[st] += 1
        out["scored"] += 1
        rows.append({"user_id": user_id, "source_item_id": sid, "run_date": today.isoformat(), "origin": origin,
                     "cost_breakdown_json": econ.breakdown(), "domestic_price_krw": econ.domestic_price_krw, "margin_rate": econ.margin_rate,
                     "suggested_price_krw": econ.suggested_price_krw, "score": econ.score, "score_parts_json": econ.score_parts,
                     "flags": econ.flags, "status": st})
    if rows:
        c.table("candidates").upsert(rows, on_conflict="user_id,source_item_id,run_date").execute()
    out["rates"] = rates.source
    return out


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", type=int)
    a = ap.parse_args(argv)
    from app.db import current_user_id, user_client
    from app.user_settings import ensure_user_settings

    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    r = run(c, uid, only_item=a.item)
    print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
