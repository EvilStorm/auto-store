"""③ 국내 조회기 (DESIGN.md 6-③). LLM 0회.

  python -m app.pipeline.domestic --item 123          # source_items.id 하나
  python -m app.pipeline.domestic --pending [--limit 50]   # 정규화됐는데 시장 신호가 없거나 오래된 것

흐름: 검색어별 공용 캐시(naver_queries, TTL) → 미스만 네이버 크롤링 → naver_items upsert
   → 썸네일 pHash · CLIP → images (nv_mid 당 1회) → 소스 대표 이미지도 images
   → 매칭 = CLIP 코사인 + 핵심 숫자 규칙 → matches → market_signals
판정 로직(judge)은 DB · 네트워크 없이 순수 함수라 테스트로 고정한다.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app import repo
from app.adapters import naver_crawl
from app.config import settings
from app.taxonomy import units
from app.vision import clip, phash


# ───────────────────────── 순수 판정 로직 ─────────────────────────
@dataclass
class Candidate:
    nv_mid: str
    title: str
    price: int
    mall: str = ""
    review_count: int | None = None
    wish_count: int | None = None
    seller_count: int | None = None
    cat_id: str | None = None
    image_url: str = ""
    clip: list[float] | None = None
    phash: str | None = None
    is_ad: bool = False


@dataclass
class Judgement:
    exact: list[dict] = field(default_factory=list)
    similar: list[dict] = field(default_factory=list)
    same_image_sellers: int = 0
    total: int = 0

    def signals(self) -> dict:
        basis = self.exact or self.similar
        prices = [r["price"] for r in basis if r.get("price")]
        reviews = [r["review_count"] for r in basis if r.get("review_count")]
        wishes = [r["wish_count"] for r in basis if r.get("wish_count")]
        sellers = [r["seller_count"] for r in basis if r.get("seller_count")]
        cats = [r["cat_id"] for r in basis if r.get("cat_id")]
        return {
            "exact_count": len(self.exact),
            "similar_count": len(self.similar),
            "total_results": self.total,
            "same_image_sellers": self.same_image_sellers,
            "review_avg": int(statistics.mean(reviews)) if reviews else None,
            "review_top": max(reviews) if reviews else None,
            "wish_top": max(wishes) if wishes else None,
            "seller_count_max": max(sellers) if sellers else None,
            "price_mean": int(statistics.mean(prices)) if prices else None,
            "price_median": int(statistics.median(prices)) if prices else None,
            "price_min": min(prices) if prices else None,
            "basis_type": "exact" if self.exact else ("similar" if self.similar else None),
            "naver_cat_id": max(set(cats), key=cats.count) if cats else None,
        }


def judge(source_clip: list[float] | None, source_phash: str | None, source_numbers: dict, cands: list[Candidate], *,
          exact_threshold: float = 0.90, similar_threshold: float = 0.80, number_tol: float = 0.08) -> Judgement:
    """CLIP 코사인으로 exact/similar, 핵심 숫자(용량 등)가 다르면 한 단계 강등. CLIP 이 없으면 pHash 동일 → exact, 숫자 일치 → similar."""
    j = Judgement(total=len(cands))
    malls_same_image: set[str] = set()
    for c in cands:
        if c.is_ad:
            continue
        sim = clip.cosine(source_clip, c.clip)
        same_pic = phash.same_image(source_phash, c.phash)
        if same_pic:
            malls_same_image.add(c.mall or c.nv_mid)
        cand_numbers = units.extract_numbers(c.title)
        agree = units.numbers_agree(source_numbers, cand_numbers, "capacity_ml", tol=number_tol)
        reasons = []
        if sim is not None:
            rel = "exact" if sim >= exact_threshold else "similar" if sim >= similar_threshold else None
            reasons.append(f"이미지 유사도 {sim:.2f}")
        else:
            rel = "exact" if same_pic else ("similar" if agree else None)
            reasons.append("동일 사진" if same_pic else "CLIP 없음")
        if same_pic and rel != "exact":
            rel = "exact"
            reasons.append("동일 사진")
        if agree is False and rel == "exact":
            rel = "similar"
            reasons.append("용량 불일치 → 유사")
        elif agree is True:
            reasons.append("용량 일치")
        if rel is None:
            continue
        row = {"nv_mid": c.nv_mid, "title": c.title, "price": c.price, "mall": c.mall, "review_count": c.review_count,
               "wish_count": c.wish_count, "seller_count": c.seller_count, "cat_id": c.cat_id,
               "similarity": round(sim, 3) if sim is not None else None, "reason": " · ".join(reasons),
               "matched_numbers": {"capacity_agree": agree}}
        (j.exact if rel == "exact" else j.similar).append(row)
    j.same_image_sellers = len(malls_same_image)
    j.exact.sort(key=lambda r: -(r["similarity"] or 0))
    j.similar.sort(key=lambda r: -(r["similarity"] or 0))
    return j


# ───────────────────────── DB · 네트워크가 있는 부분 ─────────────────────────
def _now():
    return datetime.now(timezone.utc)


def _fresh(ts: str | None, days: int) -> bool:
    if not ts:
        return False
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return False
    return _now() - t < timedelta(days=days)


def cached_queries(c, queries: list[str], ttl_days: int) -> tuple[dict[str, list[str]], list[str]]:
    """{query: nv_mids} (신선한 것만), 그리고 크롤링해야 할 검색어 목록."""
    rows = c.table("naver_queries").select("query, fetched_at, nv_mids, blocked").in_("query", queries).execute().data
    have = {r["query"]: r for r in rows}
    hit, miss = {}, []
    for q in queries:
        r = have.get(q)
        if r and _fresh(r.get("fetched_at"), ttl_days) and not r.get("blocked"):
            hit[q] = list(r.get("nv_mids") or [])
        else:
            miss.append(q)
    return hit, miss


def crawl_and_store(c, queries: list[str], profile_dir=None) -> dict[str, list[str]]:
    results = naver_crawl.search(queries, profile_dir=profile_dir)
    out: dict[str, list[str]] = {}
    for r in results:
        rows = []
        mids = []
        for it in r.items:
            if not it.nv_mid:
                continue
            mids.append(it.nv_mid)
            rows.append({"nv_mid": it.nv_mid, "title": it.title[:300], "price": it.price, "shipping_krw": it.shipping_krw,
                         "rating": it.rating, "review_count": it.review_count, "wish_count": it.wish_count,
                         "seller_count": it.seller_count, "mall": it.mall[:100] if it.mall else None, "link": it.link,
                         "image_url": it.image, "cat_id": it.cat_id or None, "kind": it.kind, "is_ad": it.is_ad,
                         "fetched_at": _now().isoformat()})
        if rows:
            # 같은 결과 안에 nv_mid 중복이 있으면 한 번만
            dedup = {r["nv_mid"]: r for r in rows}
            c.table("naver_items").upsert(list(dedup.values()), on_conflict="nv_mid").execute()
        c.table("naver_queries").upsert({"query": r.query, "fetched_at": _now().isoformat(), "nv_mids": list(dict.fromkeys(mids)),
                                         "blocked": r.blocked}, on_conflict="query").execute()
        out[r.query] = list(dict.fromkeys(mids))
    return out


def ensure_images(c, refs: list[tuple[str, str, str]], *, want_clip: bool) -> dict[tuple[str, str], dict]:
    """refs = [(kind, ref_id, url)]. images 에 없거나 clip 이 비어 있으면 내려받아 pHash · CLIP 계산해 upsert. 반환 {(kind, ref_id): row}."""
    if not refs:
        return {}
    by_kind: dict[str, list[str]] = {}
    for k, rid, _ in refs:
        by_kind.setdefault(k, []).append(rid)
    have: dict[tuple[str, str], dict] = {}
    for k, ids in by_kind.items():
        for r in c.table("images").select("kind, ref_id, url, phash, clip, logo_detected").eq("kind", k).in_("ref_id", ids).execute().data:
            r["clip"] = clip.from_pgvector(r.get("clip"))
            have[(r["kind"], r["ref_id"])] = r
    todo = [(k, rid, url) for k, rid, url in refs if url and ((k, rid) not in have or (want_clip and not have[(k, rid)].get("clip")))]
    blobs: list[tuple[tuple[str, str, str], bytes]] = []
    for k, rid, url in todo:
        ib = phash.fetch(url, referer="https://search.naver.com/" if k == "naver" else None)
        if ib:
            blobs.append(((k, rid, url), ib.data))
    vecs = clip.embed_bytes([b for _, b in blobs]) if (want_clip and blobs) else [None] * len(blobs)
    rows = []
    for ((k, rid, url), data), vec in zip(blobs, vecs):
        ph = phash.phash_hex(data)
        row = {"kind": k, "ref_id": rid, "url": url, "phash": phash.to_int64(ph) if ph else None,
               "clip": clip.to_pgvector(vec) if vec else None, "fetched_at": _now().isoformat()}
        rows.append(row)
        have[(k, rid)] = {**row, "clip": vec, "phash": row["phash"]}
    if rows:
        c.table("images").upsert(rows, on_conflict="kind,ref_id").execute()
    return have


def lookup(c, source_item: dict, normalized: dict, *, ttl_days: int | None = None, naver_profile_dir=None) -> dict:
    """source_items 행 + normalized 행 → matches · market_signals 저장. 반환 {signals, exact, similar, crawled, cached}."""
    ttl = ttl_days if ttl_days is not None else settings.naver_cache_ttl_days
    queries = [q for q in (normalized.get("search_queries") or []) if q][:3]
    if not queries:
        return {"skipped": "검색어 없음"}
    hit, miss = cached_queries(c, queries, ttl)
    crawled = crawl_and_store(c, miss, profile_dir=naver_profile_dir) if miss else {}
    mids: list[str] = []
    for q in queries:
        for m in (hit.get(q) or crawled.get(q) or []):
            if m not in mids:
                mids.append(m)
    mids = mids[: settings.naver_top_n * 2]
    if not mids:
        sig = Judgement(total=0).signals() | {"source_item_id": source_item["id"], "computed_at": _now().isoformat()}
        c.table("market_signals").upsert(sig, on_conflict="source_item_id").execute()
        return {"signals": sig, "exact": [], "similar": [], "crawled": list(crawled), "cached": list(hit), "note": "네이버 결과 없음"}
    items = {r["nv_mid"]: r for r in c.table("naver_items").select("*").in_("nv_mid", mids).execute().data}

    want_clip = clip.available()
    sid = str(source_item["id"])
    refs = [("source", sid, source_item.get("main_image_url") or "")] + [("naver", m, items[m].get("image_url") or "") for m in mids if m in items]
    imgs = ensure_images(c, refs, want_clip=want_clip)
    src_img = imgs.get(("source", sid), {})
    src_ph = phash.from_int64(src_img["phash"]) if src_img.get("phash") is not None else None
    cands = []
    for m in mids:
        it = items.get(m)
        if not it:
            continue
        im = imgs.get(("naver", m), {})
        cands.append(Candidate(
            nv_mid=m, title=it["title"], price=it["price"], mall=it.get("mall") or "", review_count=it.get("review_count"),
            wish_count=it.get("wish_count"), seller_count=it.get("seller_count"), cat_id=it.get("cat_id"), image_url=it.get("image_url") or "",
            clip=im.get("clip"), phash=phash.from_int64(im["phash"]) if im.get("phash") is not None else None, is_ad=bool(it.get("is_ad")),
        ))
    j = judge(src_img.get("clip"), src_ph, normalized.get("key_numbers_json") or {}, cands,
              exact_threshold=settings.exact_threshold, similar_threshold=settings.similar_threshold)

    method = "clip" if want_clip else "rule"
    match_rows = [{"source_item_id": source_item["id"], "nv_mid": r["nv_mid"], "relation": rel, "method": method,
                   "similarity": r["similarity"], "matched_numbers_json": r["matched_numbers"], "reason": r["reason"], "computed_at": _now().isoformat()}
                  for rel, rows in (("exact", j.exact), ("similar", j.similar)) for r in rows]
    c.table("matches").delete().eq("source_item_id", source_item["id"]).eq("method", method).execute()
    if match_rows:
        c.table("matches").upsert(match_rows, on_conflict="source_item_id,nv_mid,method").execute()
    sig = j.signals() | {"source_item_id": source_item["id"], "computed_at": _now().isoformat()}
    c.table("market_signals").upsert(sig, on_conflict="source_item_id").execute()
    return {"signals": sig, "exact": j.exact, "similar": j.similar, "crawled": list(crawled), "cached": list(hit), "method": method}


def pending_items(c, limit: int, stale_days: int) -> list[tuple[dict, dict]]:
    """정규화됐고 제외되지 않았는데 시장 신호가 없거나 오래된 상품."""
    norm = c.table("source_items_normalized").select("*").is_("excluded_reason", "null").order("normalized_at", desc=True).limit(limit * 3).execute().data
    ids = [n["source_item_id"] for n in norm]
    if not ids:
        return []
    sigs = {s["source_item_id"]: s for s in c.table("market_signals").select("source_item_id, computed_at").in_("source_item_id", ids).execute().data}
    items = {i["id"]: i for i in c.table("source_items").select("*").in_("id", ids).execute().data}
    out = []
    for n in norm:
        s = sigs.get(n["source_item_id"])
        if s and _fresh(s.get("computed_at"), stale_days):
            continue
        if n["source_item_id"] in items:
            out.append((items[n["source_item_id"]], n))
        if len(out) >= limit:
            break
    return out


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", type=int)
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args(argv)
    from app.db import user_client

    c = user_client()
    print(f"CLIP {'사용' if clip.available() else '없음 → pHash · 숫자 규칙만'} · 캐시 TTL {settings.naver_cache_ttl_days}일 · 임계 {settings.exact_threshold}/{settings.similar_threshold}")
    pairs = []
    if a.item:
        it = c.table("source_items").select("*").eq("id", a.item).limit(1).execute().data
        nm = c.table("source_items_normalized").select("*").eq("source_item_id", a.item).limit(1).execute().data
        if not it or not nm:
            print("상품 또는 정규화 행이 없습니다")
            return 1
        pairs = [(it[0], nm[0])]
    elif a.pending:
        pairs = pending_items(c, a.limit, settings.naver_cache_ttl_days)
    else:
        ap.print_help()
        return 1
    print(f"대상 {len(pairs)}건")
    naver_prof = settings.profiles_dir / "naver"
    for it, nm in pairs:
        r = lookup(c, it, nm, naver_profile_dir=naver_prof if naver_prof.exists() else None)
        if r.get("skipped"):
            print(f"  [{it['id']}] 건너뜀: {r['skipped']}")
            continue
        s = r["signals"]
        print(f"  [{it['id']}] {it['title_raw'][:30]} · 정확 {s['exact_count']} 유사 {s['similar_count']} / {s['total_results']} · 동일사진 {s['same_image_sellers']} · "
              f"가격 평균 {s['price_mean']} · 리뷰 최대 {s['review_top']} · 크롤 {len(r['crawled'])} 캐시 {len(r['cached'])} · {r.get('method')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
