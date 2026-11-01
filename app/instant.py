"""URL 즉시 분석 (DESIGN.md 2장 "별도 입구"). v3: 이력은 Supabase analysis_requests, 결과는 일반 후보와 같은 candidates 행.

  python -m app.instant <상품URL>                 # 등록 소스면 어댑터 경로(AI 0회), 미등록 사이트면 범용 LLM 경로
  python -m app.instant --queue [--limit 5]       # 텔레그램 · 웹에서 큐에 쌓인(queued) 요청 처리 → 텔레그램 카드
  python -m app.instant --recent [N]              # 최근 이력
  python -m app.instant --fetch-only <URL>        # 페이지 스냅샷만 (로그인 · DB 불필요)

등록 소스 경로: 어댑터 detail → 공용 source_items · source_item_details → ② 사전 정규화 → ③ 국내 조회(캐시 · CLIP) → ④ 내 점수(origin=instant) → 카드
미등록 경로:   범용 스냅샷 → page_extracts 캐시(url · 텍스트 해시) 또는 LLM 추출(ai_results 캐시) → LLM 정규화 → 공용 source_items(소스 = host) → ③ → ④ → 카드
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from app import repo
from app.config import settings


def _now():
    return datetime.now(timezone.utc).isoformat()


def _registrable(host: str) -> str:
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def find_source(c, url: str) -> dict | None:
    """공용 sources 중 URL 의 등록 도메인(1688.com · aliexpress.com)이 같은 것."""
    host = _registrable(urlparse(url).netloc)
    for s in c.table("sources").select("id, base_url, adapter_key, auth_mode").execute().data:
        if _registrable(urlparse(s["base_url"]).netloc) == host:
            return s
    return None


# ───────────────────────── 등록 소스 경로 (AI 0회) ─────────────────────────
def _detail_via_adapter(source: dict, url: str, *, headed: bool = False):
    from app.pipeline.collector import make_adapter
    from app.sources.base import RawDetail

    us = {}
    with make_adapter(source["adapter_key"], us, headed=headed) as ad:
        d: RawDetail = ad.detail(url)
    return d


def _store_detail(c, d) -> int:
    id_map = repo.upsert_source_items(c, [d])
    sid = id_map[d.item_id]
    c.table("source_item_details").upsert({
        "source_item_id": sid, "options_json": d.options, "images": d.images[:30], "attrs_full_json": d.attrs_full,
        "package_weight_g": _weight_g(d.package_weight_raw or d.weight_raw), "fetched_at": _now(),
    }, on_conflict="source_item_id").execute()
    return sid


def _weight_g(raw: str) -> int | None:
    from app.taxonomy import units

    n = units.extract_numbers(raw or "")
    w = units.primary(n, "weight_g")
    return int(w) if w else None


# ───────────────────────── 미등록 사이트 경로 (범용 LLM, 캐시) ─────────────────────────
def _extract_generic(c, llm, snap):
    """page_extracts(url, 텍스트 해시) 캐시 → 없으면 LLM 추출(그 호출도 ai_results 캐시)."""
    from app.pipeline.extract import RawDetail as RawDetailModel
    from app.pipeline.extract import extract_raw

    h = hashlib.sha256(snap.text.encode("utf-8")).hexdigest()
    rows = c.table("page_extracts").select("raw_json").eq("url", snap.final_url).eq("text_hash", h).limit(1).execute().data
    if rows:
        return RawDetailModel.model_validate(rows[0]["raw_json"]), True
    raw = extract_raw(llm, snap)
    c.table("page_extracts").upsert({"url": snap.final_url, "text_hash": h, "raw_json": raw.model_dump(mode="json")}, on_conflict="url,text_hash").execute()
    return raw, False


def _ensure_generic_source(c, host: str) -> dict:
    rows = c.table("sources").select("id, base_url, adapter_key").eq("id", host).limit(1).execute().data
    if rows:
        return rows[0]
    row = {"id": host, "name": host, "country": "CN", "currency": "USD", "base_url": f"https://{host}", "adapter_key": "llm_extract", "auth_mode": "none"}
    try:
        return c.table("sources").insert(row).execute().data[0]
    except Exception as e:
        raise RuntimeError(f"미등록 사이트 {host} 를 소스로 등록하지 못했습니다(admin 필요): {type(e).__name__}") from e


# ───────────────────────── 공통 후단 ─────────────────────────
def _normalize_and_store(c, d, sid: int, source_id: str, *, generic_norm=None):
    """② 사전 정규화(등록 소스) 또는 LLM 정규화 결과(미등록) → source_items_normalized."""
    from app.pipeline import normalizer
    from app.taxonomy import dictionary

    dct = dictionary.from_db(c)
    raw = d.to_dict() if hasattr(d, "to_dict") else d
    cat = None
    crumbs = (raw.get("category_raw") or "")
    for part in reversed([p.strip() for p in crumbs.replace(">", "/").split("/") if p.strip()]):
        cid = dct.category_for_term(part)
        if cid:
            cat = dct.categories.get(cid)
            break
    if cat is None:  # 빵부스러기가 없으면 제목의 카테고리 별칭(保温杯 …)으로
        cid = dct.category_for_text(raw.get("title_raw") or "")
        cat = dct.categories.get(cid) if cid else None
    if generic_norm is not None:
        # 미등록 경로: LLM 이 준 검색어 · 재질 · 품목을 그대로 행으로
        n_row = {
            "source_item_id": sid, "dict_version": dct.dict_version, "title_clean": generic_norm.title_ko,
            "key_numbers_json": {"key_attributes": generic_norm.key_attributes}, "material_code": generic_norm.material_code if generic_norm.material_code != "unknown" else None,
            "item_type": generic_norm.item_type, "canonical_category_id": cat.id if cat else None, "search_queries": generic_norm.search_queries[:3],
            "brand_text_hit": ("llm" if generic_norm.brand_detected else None),
            "excluded_reason": ("brand_text" if generic_norm.brand_detected else (generic_norm.item_type if generic_norm.requirement_status == "excluded" else None)),
            "mapping_pending": cat is None,
        }
        repo.upsert_normalized(c, [n_row])
        return n_row
    ruleset = repo.active_ruleset(c, source_id, cat.id if cat else None)
    n = normalizer.normalize(raw, cat, dct, rules=(ruleset or {}).get("rules_json"), ruleset_version=(ruleset or {}).get("version"))
    row = normalizer.to_row(sid, n)
    repo.upsert_normalized(c, [row])
    if n.missing:
        repo.enqueue_missing(c, n.missing, source_id, sid)
    return row


def _lookup_and_score(c, uid: str, sid: int, item: dict, n_row: dict) -> dict | None:
    from app.pipeline import domestic, scoring

    prof = settings.profiles_dir / "naver"
    domestic.lookup(c, item, n_row, naver_profile_dir=prof if prof.exists() else None)
    scoring.run(c, uid, only_item=sid, origin="instant")
    rows = c.table("candidates").select("*").eq("source_item_id", sid).eq("run_date", date.today().isoformat()).limit(1).execute().data
    return rows[0] if rows else None


def _card(c, item: dict, n_row: dict, cand: dict | None) -> str:
    from app.pipeline.notify import render_card

    sig = (c.table("market_signals").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    matches = c.table("matches").select("nv_mid, relation, method, similarity, reason").eq("source_item_id", item["id"]).execute().data
    nv = {x["nv_mid"]: x for x in c.table("naver_items").select("nv_mid, title, price, review_count").in_("nv_mid", [m["nv_mid"] for m in matches]).execute().data} if matches else {}
    merged = sorted([{**nv.get(m["nv_mid"], {}), **m} for m in matches if m["nv_mid"] in nv], key=lambda m: (m["relation"] != "exact", -(m.get("similarity") or 0)))
    if cand is None:
        cand = {"cost_breakdown_json": {}, "flags": ["no_domestic_price"]}
    return render_card(item, n_row, sig, cand, matches=merged, logo=None, source_name=item.get("source_id", ""))


def _today_count(c, uid: str) -> int:
    return c.table("analysis_requests").select("*", count="exact").gte("requested_at", date.today().isoformat()).limit(1).execute().count or 0


def analyze(c, uid: str, url: str, *, channel: str = "cli", headed: bool = False, request_id: int | None = None) -> dict:
    """1건 분석. 반환 {status, card, candidate_id, summary, error, request_id}."""
    if request_id is None:
        if _today_count(c, uid) >= settings.instant_daily_limit:
            return {"status": "failed", "error": f"오늘 즉시 분석 상한({settings.instant_daily_limit}건) 도달"}
        request_id = c.table("analysis_requests").insert({"user_id": uid, "channel": channel, "url": url, "status": "running"}).execute().data[0]["id"]
    else:
        c.table("analysis_requests").update({"status": "running"}).eq("id", request_id).execute()
    out: dict = {"request_id": request_id, "status": "failed"}
    try:
        source = find_source(c, url)
        if source and source["adapter_key"] in ("1688",):
            d = _detail_via_adapter(source, url, headed=headed)
            sid = _store_detail(c, d)
            item = c.table("source_items").select("*").eq("id", sid).limit(1).execute().data[0]
            n_row = _normalize_and_store(c, d, sid, source["id"])
            path = "adapter"
        else:
            from app.adapters.llm import get_llm
            from app.ai_cache import SupabaseCache, set_backend
            from app.pipeline.extract import normalize as llm_normalize
            from app.sources.base import RawListing
            from app.sources.fetch import fetch_page

            set_backend(SupabaseCache(c))
            llm = get_llm()
            snap = fetch_page(url, headed=headed)
            if snap.blocked_hint and (len(snap.text) < 200 or "없음" in snap.blocked_hint):
                raise RuntimeError(f"페이지를 읽지 못함: {snap.blocked_hint}")
            raw, cached = _extract_generic(c, llm, snap)
            if not raw.is_product_page:
                raise RuntimeError(f"상품 페이지가 아님: {raw.page_problem}")
            gnorm = llm_normalize(llm, raw, snap)
            host = urlparse(snap.final_url).netloc.lower()
            src = _ensure_generic_source(c, host)
            li = RawListing(source_id=src["id"], item_id=hashlib.sha1(snap.final_url.encode()).hexdigest()[:16], url=snap.final_url, title_raw=raw.title_raw, lang=raw.lang,
                            price_raw="", price_tiers=[t.model_dump() for t in raw.price_tiers], currency=raw.currency if raw.currency != "unknown" else "USD", moq=raw.moq,
                            image_url=snap.main_image(), category_raw=raw.category_raw or "", attrs_raw={"material": raw.material_raw, "brand": raw.brand_text}, weight_raw=str(raw.weight_g or ""))
            sid = repo.upsert_source_items(c, [li])[li.item_id]
            if raw.weight_g:
                c.table("source_item_details").upsert({"source_item_id": sid, "package_weight_g": int(raw.weight_g), "fetched_at": _now()}, on_conflict="source_item_id").execute()
            item = c.table("source_items").select("*").eq("id", sid).limit(1).execute().data[0]
            n_row = _normalize_and_store(c, li, sid, src["id"], generic_norm=gnorm)
            path = "llm" + ("(추출 캐시)" if cached else "")
            out["llm_cost_krw"] = llm.total_cost_krw()
        cand = _lookup_and_score(c, uid, sid, item, n_row)
        card = _card(c, item, n_row, cand)
        summary = {"path": path, "margin_rate": cand.get("margin_rate") if cand else None, "score": cand.get("score") if cand else None,
                   "status": cand.get("status") if cand else "no_candidate", "excluded_reason": n_row.get("excluded_reason"), "search_queries": n_row.get("search_queries")}
        c.table("analysis_requests").update({"status": "done", "source_id": item["source_id"], "source_item_id": sid, "candidate_id": cand["id"] if cand else None,
                                             "summary_json": summary}).eq("id", request_id).execute()
        out.update(status="done", card=card, candidate_id=cand["id"] if cand else None, summary=summary, item_id=sid)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        c.table("analysis_requests").update({"status": "failed", "error": err[:500]}).eq("id", request_id).execute()
        out.update(error=err, trace=traceback.format_exc()[-1500:])
    return out


def process_queue(c, uid: str, *, limit: int = 5, bot=None) -> list[dict]:
    """queued 요청을 순서대로 분석. bot 이 있으면 카드를 텔레그램으로."""
    from app.adapters.telegram import callback_data

    rows = c.table("analysis_requests").select("id, url, channel").eq("status", "queued").order("requested_at").limit(limit).execute().data
    results = []
    for r in rows:
        res = analyze(c, uid, r["url"], channel=r["channel"], request_id=r["id"])
        results.append(res)
        if bot is not None:
            if res["status"] == "done":
                buttons = [[("승인", callback_data("c", res["candidate_id"], "approve")), ("거절", callback_data("c", res["candidate_id"], "reject")), ("보류", callback_data("c", res["candidate_id"], "hold"))]] if res.get("candidate_id") else None
                item = c.table("source_items").select("main_image_url").eq("id", res["item_id"]).limit(1).execute().data
                img = (item[0]["main_image_url"] if item else "") or ""
                bot.send_photo(img, res["card"], buttons=buttons) if img else bot.send_text(res["card"], buttons=buttons)
            else:
                bot.send_text(f"즉시 분석 실패: {r['url'][:80]}\n{res.get('error', '')[:300]}")
    return results


def recent(c, n: int = 10) -> list[dict]:
    return c.table("analysis_requests").select("id, requested_at, channel, url, status, summary_json, decision, error").order("requested_at", desc=True).limit(n).execute().data


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="URL 즉시 분석")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--fetch-only", action="store_true", help="페이지 스냅샷만 출력 (로그인 · DB 불필요)")
    ap.add_argument("--queue", action="store_true", help="큐에 쌓인 요청 처리")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--recent", nargs="?", const=10, type=int)
    ap.add_argument("--telegram", action="store_true", help="--queue 결과를 텔레그램으로도")
    a = ap.parse_args(argv)

    if a.fetch_only:
        if not a.url:
            ap.print_help()
            return 1
        from app.sources.fetch import fetch_page

        snap = fetch_page(a.url, headed=a.headed)
        print(json.dumps({"final_url": snap.final_url, "title": snap.title, "text_chars": len(snap.text), "text_head": snap.text[:1200], "images": snap.images[:8],
                          "og_image": snap.og_image, "blocked_hint": snap.blocked_hint}, ensure_ascii=False, indent=2))
        return 0

    from app.db import current_user_id, user_client
    from app.user_settings import ensure_user_settings

    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    if a.recent is not None:
        for r in recent(c, a.recent):
            s = r.get("summary_json") or {}
            m = f"{s['margin_rate'] * 100:.0f}%" if s.get("margin_rate") is not None else "-"
            print(f"#{r['id']} {r['requested_at'][:16]} {r['channel']:<8} {r['status']:<7} 마진 {m:>5} 점수 {s.get('score') or '-':<6} {s.get('path') or ''} {r['url'][:60]} {r.get('error') or ''}")
        return 0
    if a.queue:
        bot = None
        if a.telegram:
            from app.adapters.telegram import bot_from

            bot = bot_from(c)
        res = process_queue(c, uid, limit=a.limit, bot=bot)
        for r in res:
            print(r.get("card") or r.get("error"), "\n")
        print(f"처리 {len(res)}건")
        return 0
    if not a.url:
        ap.print_help()
        return 1
    res = analyze(c, uid, a.url, headed=a.headed)
    if res["status"] == "done":
        print(res["card"])
        print(f"\n[{res['summary']['path']}] analysis_requests #{res['request_id']} · candidate {res.get('candidate_id')}" + (f" · LLM {res['llm_cost_krw']:.0f}원" if res.get("llm_cost_krw") else " · LLM 0회"))
        return 0
    print(f"실패: {res.get('error')}")
    if res.get("trace"):
        print(res["trace"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
