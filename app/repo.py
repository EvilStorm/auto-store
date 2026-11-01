"""Supabase 데이터 접근 (얇은 함수 모음). 파이프라인은 supabase-py 호출을 직접 하지 않고 여기를 거친다."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.sources.base import RawListing


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 관심 카테고리 (개인) ──
def my_watch_categories(c) -> list[dict]:
    """enabled 관심 카테고리 + 소스 카테고리 + 소스 정의 + 내 소스 설정을 한 번에."""
    rows = c.table("user_watch_categories").select(
        "id, max_pages, enabled, extra_keywords_ko, source_categories(id, source_id, label_raw, url, canonical_category_id, sources(id, name, adapter_key, base_url, auth_mode))"
    ).eq("enabled", True).execute().data
    out = []
    for r in rows:
        sc = r.get("source_categories") or {}
        src = sc.get("sources") or {}
        out.append({
            "watch_id": r["id"], "max_pages": r["max_pages"], "extra_keywords_ko": r.get("extra_keywords_ko") or [],
            "source_category_id": sc.get("id"), "source_id": sc.get("source_id"), "label_raw": sc.get("label_raw"),
            "url": sc.get("url"), "canonical_category_id": sc.get("canonical_category_id"),
            "adapter_key": src.get("adapter_key"), "auth_mode": src.get("auth_mode"),
        })
    return out


def my_user_sources(c) -> dict[str, dict]:
    rows = c.table("user_sources").select("*").execute().data
    return {r["source_id"]: r for r in rows}


# ── 공용 수집 ──
def upsert_source_items(c, listings: list[RawListing]) -> dict[str, int]:
    """(source_id, source_item_id) 로 upsert. 반환 {item_id: source_items.id}. last_seen_at 은 지금."""
    if not listings:
        return {}
    rows = []
    for li in listings:
        r = li.to_row()
        r["last_seen_at"] = now_iso()
        rows.append(r)
    res = c.table("source_items").upsert(rows, on_conflict="source_id,source_item_id").execute()
    return {r["source_item_id"]: r["id"] for r in (res.data or [])}


def existing_normalized(c, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = c.table("source_items_normalized").select("source_item_id, dict_version, ruleset_version, normalized_at").in_("source_item_id", ids).execute().data
    return {r["source_item_id"]: r for r in rows}


def upsert_normalized(c, rows: list[dict]) -> int:
    if not rows:
        return 0
    res = c.table("source_items_normalized").upsert(rows, on_conflict="source_item_id").execute()
    return len(res.data or [])


def enqueue_missing(c, missing: list[dict], source_id: str | None, sample_item_id: int | None) -> int:
    """mapping_queue 에 (kind, term, lang) 유니크로 추가. 이미 있으면 무시."""
    n = 0
    for m in missing:
        row = {"kind": m["kind"], "term": m["term"][:200], "lang": m.get("lang", "zh"), "source_id": source_id,
               "sample_item_id": sample_item_id, "suggested_id_or_code": m.get("suggested"), "confidence": m.get("confidence")}
        try:
            c.table("mapping_queue").upsert(row, on_conflict="kind,term,lang", ignore_duplicates=True).execute()
            n += 1
        except Exception:
            pass
    return n


# ── 규칙 세트 ──
def active_ruleset(c, source_id: str, canonical_category_id: str | None, kind: str = "normalize") -> dict | None:
    """카테고리 세트 → 소스 기본 세트 순. 없으면 None (DEFAULT_RULES 사용)."""
    if canonical_category_id:
        rows = c.table("rulesets").select("id, version, rules_json").eq("source_id", source_id).eq("canonical_category_id", canonical_category_id).eq("kind", kind).eq("status", "active").limit(1).execute().data
        if rows:
            return rows[0]
    rows = c.table("rulesets").select("id, version, rules_json").eq("source_id", source_id).is_("canonical_category_id", "null").eq("kind", kind).eq("status", "active").limit(1).execute().data
    return rows[0] if rows else None


def record_coverage(c, ruleset_id: int, coverage: dict) -> None:
    try:
        c.table("rulesets").update({"coverage_json": coverage}).eq("id", ruleset_id).execute()
    except Exception:
        pass


# ── 실행 로그 · 잠금 ──
def log_run(c, user_id: str, kind: str, run_date: date, counts: dict, *, source_id: str | None = None, stage: str | None = None,
            error: str | None = None, pc_name: str | None = None, started_at: str | None = None) -> None:
    c.table("run_logs").insert({
        "user_id": user_id, "run_date": run_date.isoformat(), "kind": kind, "source_id": source_id, "stage": stage,
        "counts_json": counts, "error": error, "pc_name": pc_name, "started_at": started_at or now_iso(), "finished_at": now_iso(),
    }).execute()


def acquire_lock(c, run_date: date, kind: str, pc_name: str) -> bool:
    return bool(c.rpc("acquire_batch_lock", {"p_run_date": run_date.isoformat(), "p_kind": kind, "p_pc_name": pc_name}).execute().data)
