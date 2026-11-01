"""⑤ 1차 알림 (DESIGN.md 6-⑤): 상위 N건 선정 → N건만 로고 비전(pHash 캐시) · 선택적 LLM 매칭 재판정 → 텔레그램 카드.

  python -m app.pipeline.notify                # 오늘 후보 중 미전송 상위 N건 발송
  python -m app.pipeline.notify --dry-run      # 카드 텍스트만 출력 (LLM 도 호출 안 함)
  python -m app.pipeline.notify --no-llm       # 로고 · 재판정 없이 발송

AI 가 쓰이는 유일한 지점: 로고 확인(images.logo_* 에 1회) · 재판정(matches.method=llm). 둘 다 ai_results 캐시 경유.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.adapters.llm.base import LLM, ImageRef
from app.config import settings
from app.vision import phash

FLAG_KO = {
    "weight_unknown": "무게 미확인 → 배대지 요금 미반영", "near_customs_limit": "과세가격 130달러 초과 (경계)",
    "over_customs_limit": "150달러 초과 → 관부가세 반영", "rate_stale": "환율이 오래됨", "requirement_needed": "요건 필요 (KC 등)",
    "requirement_unknown": "요건 미확정", "brand_detected": "브랜드 텍스트 감지", "price_is_reference": "국내가는 유사 상품 기준(참고치)",
    "few_matches": "비교 상품 1~2건뿐 (가격 신뢰 낮음)", "no_domestic_price": "국내 비교 상품 없음", "weight_estimated": "무게는 카테고리 기본값(추정)",
}


class LogoCheck(BaseModel):
    detected: bool = Field(description="상품 자체에 타사 브랜드 로고 · 캐릭터 · 상표가 보이는가 (판매자 상호 · 워터마크는 제외)")
    reason: str = Field(description="한 줄 근거")


class RejudgeItem(BaseModel):
    nv_mid: str
    relation: Literal["exact", "similar", "unrelated"]
    reason: str


class Rejudge(BaseModel):
    items: list[RejudgeItem]
    overall_reason: str


SYSTEM_LOGO = "너는 구매대행 상품 검수자다. 이미지에 타사 브랜드 로고 · 캐릭터(디즈니 · 산리오 등) · 상표가 상품 자체에 인쇄 · 각인되어 있는지 본다. 판매자 상호 · 워터마크 · 포장 문구는 로고가 아니다."
SYSTEM_REJUDGE = (
    "너는 해외 소스 상품과 네이버 쇼핑 결과를 비교해 같은 상품인지 판정한다. exact = 동일 상품(같은 공산품: 용량 · 형태 · 재질 · 구성 일치), "
    "similar = 같은 종류의 비슷한 상품, unrelated = 다른 종류. 이미지가 있으면 이미지 일치를 가장 중시하고 가격 · 브랜드명은 판정에 쓰지 않는다."
)


def _won(v) -> str:
    return "-" if v is None else f"{int(v):,}원"


def render_card(item: dict, norm: dict, sig: dict, cand: dict, *, matches: list[dict], logo: dict | None, source_name: str = "1688") -> str:
    cb = cand.get("cost_breakdown_json") or {}
    flags = list(cand.get("flags") or [])
    mr = cand.get("margin_rate")
    lines = [
        f"[{source_name} · {item.get('currency', 'CNY')}] {norm.get('title_clean') or item.get('title_raw', '')[:60]}",
        f"소스가  {cb.get('currency', '')} {cb.get('unit_price_src', 0):g} × 최소 {cb.get('moq', 1)}개 = {_won(cb.get('purchase_krw'))} (환율 {cb.get('rate_krw')})",
        f"국내 비교가  {_won(cand.get('domestic_price_krw'))} ({'정확' if sig.get('basis_type') == 'exact' else '유사·참고치'} · {settings.price_basis})",
        f"총원가  {_won(cb.get('total_cost_krw'))}  →  마진율 {('%.0f%%' % (mr * 100)) if mr is not None else '-'}  ·  제안 판매가 {_won(cand.get('suggested_price_krw'))}",
        f"경쟁  정확 {sig.get('exact_count', 0)} · 유사 {sig.get('similar_count', 0)} · 수집 {sig.get('total_results', 0)}건 · 동일 사진 판매자 {sig.get('same_image_sellers') if sig.get('same_image_sellers') is not None else '-'} · 판매처 최대 {sig.get('seller_count_max') or '-'}",
        f"리뷰  최대 {sig.get('review_top') or '-'} · 찜 최대 {sig.get('wish_top') or '-'}",
        f"점수  {cand.get('score') if cand.get('score') is not None else '-'}  ({', '.join(f'{k} {v:+g}' if k != 'margin' else f'마진 {v}' for k, v in (cand.get('score_parts_json') or {}).items())})",
        f"검색어  {', '.join(norm.get('search_queries') or [])}",
    ]
    if matches:
        lines.append("매칭  " + " | ".join(f"{m.get('title', '')[:20]} {m.get('price', 0):,}원 ({m.get('reason', '')[:18]})" for m in matches[:3]))
    if logo:
        lines.append(f"로고 확인  {'감지: ' + (logo.get('logo_reason') or '') if logo.get('logo_detected') else '없음'}")
    if flags:
        lines.append("주의  " + " / ".join(FLAG_KO.get(f, f) for f in flags))
    lines.append(f"링크  {item.get('url', '')}")
    return "\n".join(lines)


def logo_check(c, llm: LLM, source_item_id: int, image_url: str) -> dict | None:
    """images.logo_* 에 있으면 그대로(0회). 없으면 비전 1회(ai_results 캐시 경유) 후 저장."""
    sid = str(source_item_id)
    rows = c.table("images").select("id, phash, logo_checked_at, logo_detected, logo_reason").eq("kind", "source").eq("ref_id", sid).limit(1).execute().data
    row = rows[0] if rows else None
    if row and row.get("logo_checked_at"):
        return row
    ph = phash.from_int64(row["phash"]) if row and row.get("phash") is not None else None
    if not image_url:
        return row
    res = llm.complete_json("이 상품 이미지에 타사 브랜드 로고 · 캐릭터 · 상표가 보이는가?", LogoCheck, system=SYSTEM_LOGO,
                            images=[ImageRef(image_url, "대표 이미지", phash=ph)], purpose="logo_check", effort="low")
    upd = {"logo_checked_at": datetime.now(timezone.utc).isoformat(), "logo_detected": res.detected, "logo_reason": res.reason}
    if row:
        c.table("images").update(upd).eq("id", row["id"]).execute()
    else:
        c.table("images").upsert({"kind": "source", "ref_id": sid, "url": image_url, **upd}, on_conflict="kind,ref_id").execute()
    return {**(row or {}), **upd}


def rejudge(c, llm: LLM, item: dict, norm: dict, cands: list[dict], image_url: str) -> list[dict]:
    """상위 N건의 매칭을 LLM 으로 재판정 → matches(method=llm) 저장. 반환 exact/similar 행."""
    if not cands:
        return []
    lines = [f"[{m['nv_mid']}] {m.get('title', '')} | {m.get('price', 0):,}원 | 리뷰 {m.get('review_count') or 0}" for m in cands[:10]]
    images = [ImageRef(image_url, "소스 상품 대표 이미지")] if image_url else []
    for m in cands[:6]:
        if m.get("image_url"):
            images.append(ImageRef(m["image_url"], f"후보 [{m['nv_mid']}]"))
    prompt = f"소스 상품: {norm.get('title_clean') or item.get('title_raw')}\n핵심 숫자: {norm.get('key_numbers_json')}\n\n네이버 결과:\n" + "\n".join(lines)
    j = llm.complete_json(prompt, Rejudge, system=SYSTEM_REJUDGE, images=images, purpose="match_rejudge", effort="low")
    rel = {x.nv_mid: x for x in j.items}
    rows, out = [], []
    now = datetime.now(timezone.utc).isoformat()
    for m in cands:
        x = rel.get(m["nv_mid"])
        if not x or x.relation == "unrelated":
            continue
        rows.append({"source_item_id": item["id"], "nv_mid": m["nv_mid"], "relation": x.relation, "method": "llm", "reason": x.reason, "computed_at": now})
        out.append({**m, "relation": x.relation, "reason": x.reason})
    if rows:
        c.table("matches").upsert(rows, on_conflict="source_item_id,nv_mid,method").execute()
    return out


def pick_top(c, run_date: date, n: int, *, resend: bool = False) -> list[dict]:
    q = c.table("candidates").select("*").eq("run_date", run_date.isoformat()).eq("status", "candidate")
    if not resend:
        q = q.is_("card_sent_at", "null")
    return q.order("score", desc=True).limit(n * 2).execute().data


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(c, user_id: str, *, run_date: date | None = None, dry_run: bool = False, use_llm: bool = True, limit: int | None = None, resend: bool = False) -> dict:
    from app import repo
    from app.adapters.telegram import bot_from, callback_data

    today = run_date or date.today()
    n = min(settings.daily_candidate_n, limit) if limit else settings.daily_candidate_n
    top = pick_top(c, today, n, resend=resend)
    if not top:
        return {"sent": 0, "note": "오늘 미전송 후보 없음"}
    ids = [t["source_item_id"] for t in top]
    items = {i["id"]: i for i in c.table("source_items").select("*").in_("id", ids).execute().data}
    norms = {x["source_item_id"]: x for x in c.table("source_items_normalized").select("*").in_("source_item_id", ids).execute().data}
    sigs = {x["source_item_id"]: x for x in c.table("market_signals").select("*").in_("source_item_id", ids).execute().data}
    llm = None
    if use_llm and not dry_run:
        from app.adapters.llm import get_llm
        from app.ai_cache import SupabaseCache, set_backend

        set_backend(SupabaseCache(c))
        llm = get_llm()
    bot = None if dry_run else bot_from(c)
    sent, dropped, texts = 0, 0, []
    t_start = time.time()
    _log(f"후보 {len(top)}건 중 최대 {n}건 · LLM {'사용' if llm else '없음'} · {'dry-run' if dry_run else '발송'}")
    for cand in top:
        if sent >= n:
            break
        item, norm, sig = items.get(cand["source_item_id"]), norms.get(cand["source_item_id"]), sigs.get(cand["source_item_id"]) or {}
        if not item or not norm:
            continue
        img = item.get("main_image_url") or ""
        t0 = time.time()
        logo = None
        if llm:
            try:
                logo = logo_check(c, llm, item["id"], img)
            except Exception as e:
                logo = {"logo_detected": None, "logo_reason": f"확인 실패 {type(e).__name__}"}
            _log(f"  #{item['id']} 로고 확인 {time.time() - t0:.1f}s → {'감지' if logo and logo.get('logo_detected') else '없음'}")
            if logo and logo.get("logo_detected"):
                c.table("candidates").update({"status": "rejected_1", "decision": "brand", "decided_at": datetime.now(timezone.utc).isoformat(), "brand_vision_checked": True}).eq("id", cand["id"]).execute()
                c.table("rejections").insert({"user_id": user_id, "source_id": item["source_id"], "source_item_id": item["source_item_id"], "reason": "brand",
                                              "image_phash": logo.get("phash")}).execute()
                dropped += 1
                continue
        # 매칭 목록: llm 재판정이 있으면 그것, 없으면 clip/rule
        mrows = c.table("matches").select("nv_mid, relation, method, similarity, reason").eq("source_item_id", item["id"]).in_("relation", ["exact", "similar"]).execute().data
        nv = {m["nv_mid"] for m in mrows}
        nitems = {x["nv_mid"]: x for x in c.table("naver_items").select("nv_mid, title, price, review_count, image_url, mall").in_("nv_mid", list(nv)).execute().data} if nv else {}
        merged = [{**nitems.get(m["nv_mid"], {}), **m} for m in mrows if m["nv_mid"] in nitems]
        if llm and settings.llm_rejudge_top_n and sent < settings.llm_rejudge_top_n and merged and not any(m["method"] == "llm" for m in merged):
            t1 = time.time()
            try:
                merged = rejudge(c, llm, item, norm, sorted(merged, key=lambda m: -(m.get("similarity") or 0)), img) or merged
                _log(f"  #{item['id']} 재판정 {time.time() - t1:.1f}s → 정확 {sum(1 for m in merged if m.get('relation') == 'exact')} · 유사 {sum(1 for m in merged if m.get('relation') == 'similar')}")
            except Exception as e:
                merged.append({"title": "재판정 실패", "price": 0, "reason": type(e).__name__})
                _log(f"  #{item['id']} 재판정 실패 {type(e).__name__}")
        exact_first = sorted(merged, key=lambda m: (m.get("relation") != "exact", -(m.get("similarity") or 0)))
        text = render_card(item, norm, sig, cand, matches=exact_first, logo=logo)
        texts.append(text)
        if bot:
            t2 = time.time()
            buttons = [[("승인", callback_data("c", cand["id"], "approve")), ("거절", callback_data("c", cand["id"], "reject")), ("보류", callback_data("c", cand["id"], "hold"))]]
            bot.send_photo(img, text, buttons=buttons) if img else bot.send_text(text, buttons=buttons)
            c.table("candidates").update({"card_sent_at": datetime.now(timezone.utc).isoformat(), "brand_vision_checked": bool(llm)}).eq("id", cand["id"]).execute()
            _log(f"  #{item['id']} 발송 {time.time() - t2:.1f}s (카드 합계 {time.time() - t0:.1f}s)")
        sent += 1
    llm_calls = sum(1 for u in (llm.usage if llm else []) if not u.cache_hit)
    cost = llm.total_cost_krw() if llm else 0.0
    summary = f"오늘 카드 {sent}건 · 로고 감지로 제외 {dropped} · LLM 호출 {llm_calls}회(캐시 적중 {llm.cache_hits() if llm else 0}) · 추정 {cost:,.0f}원 · {time.time() - t_start:.0f}초"
    _log(summary)
    if bot and sent:
        bot.send_text(summary)
    if llm and not dry_run:
        try:
            for u in llm.usage:
                c.table("api_usage").insert({"user_id": user_id, "provider": u.provider, "model": u.model, "purpose": u.purpose, "input_tokens": u.input_tokens,
                                             "output_tokens": u.output_tokens, "est_cost_krw": u.est_cost_krw, "cache_hit": u.cache_hit}).execute()
        except Exception:
            pass
    repo.log_run(c, user_id, "notify", today, {"sent": sent, "dropped_brand": dropped, "llm_calls": llm_calls, "cost_krw": cost}) if not dry_run else None
    return {"sent": sent, "dropped_brand": dropped, "llm_calls": llm_calls, "cost_krw": cost, "summary": summary, "texts": texts}


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--limit", type=int, help="이번 실행에서 보낼 최대 건수 (테스트)")
    ap.add_argument("--resend", action="store_true", help="이미 보낸 카드도 다시 (테스트)")
    a = ap.parse_args(argv)
    from app.db import current_user_id, user_client
    from app.user_settings import ensure_user_settings

    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    r = run(c, uid, dry_run=a.dry_run, use_llm=not a.no_llm, limit=a.limit, resend=a.resend)
    if a.dry_run:
        for t in r.get("texts", []):
            print(t, "\n")
    if r.get("note"):
        print(r["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
