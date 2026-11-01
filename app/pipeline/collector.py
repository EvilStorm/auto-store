"""① 소스별 수집 + ② 사전 정규화 (DESIGN.md 6-①·6-②). LLM 0회.

  python -m app.pipeline.collector                 # 내 관심 카테고리 전부 (로그인 필요)
  python -m app.pipeline.collector --watch 3       # 관심 카테고리 1개만
  python -m app.pipeline.collector --dry-run       # 수집·정규화하되 DB 에 쓰지 않음 (카운트만)

흐름: 관심 카테고리(개인) × 소스 어댑터(공용 정의) → RawListing → 공용 source_items upsert
   → 정규화 필요(새 상품 · 가격 변동 · dict/ruleset 버전 낮음)만 ② → 공용 normalized upsert · 확인 큐
"""
from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date

from app import repo
from app.config import settings
from app.pipeline import normalizer
from app.sources.base import Blocked, RawListing
from app.taxonomy import dictionary


@dataclass
class Counts:
    categories: int = 0
    pages: int = 0
    listed: int = 0
    upserted: int = 0
    normalized: int = 0
    excluded: int = 0
    pending: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["errors"] = self.errors[:20]
        return d


def make_adapter(adapter_key: str, user_source: dict | None, headed: bool = False):
    us = user_source or {}
    profile = us.get("browser_profile_name") or adapter_key
    delay = (float(us.get("delay_min_s", 2)), float(us.get("delay_max_s", 6)))
    if adapter_key == "1688":
        from app.sources.s1688 import Adapter1688

        return Adapter1688(profile_dir=settings.profiles_dir / profile, headed=headed, delay_range=delay)
    raise RuntimeError(f"어댑터 미구현: {adapter_key} (1단계 발굴 MVP 는 1688)")


def normalize_batch(c, listings: list[RawListing], id_map: dict[str, int], category, d, *, ruleset: dict | None,
                    extra_keywords: list[str], source_id: str, dry_run: bool, counts: Counts) -> None:
    ids = [id_map[li.item_id] for li in listings if li.item_id in id_map]
    have = repo.existing_normalized(c, ids) if (c and not dry_run) else {}
    rows, rules = [], (ruleset or {}).get("rules_json")
    rv = (ruleset or {}).get("version")
    for li in listings:
        sid = id_map.get(li.item_id)
        if sid is None:
            continue
        prev = have.get(sid)
        if prev and prev.get("dict_version") == d.dict_version and prev.get("ruleset_version") == rv:
            continue  # 최신 — 건너뜀 (가격 변동은 source_items 에만 반영되고 정규화 결과는 그대로)
        n = normalizer.normalize(li.to_dict(), category, d, rules=rules, ruleset_version=rv, extra_keywords=extra_keywords)
        rows.append(normalizer.to_row(sid, n))
        counts.normalized += 1
        if n.excluded_reason:
            counts.excluded += 1
        if n.missing:
            counts.pending += 1
            if c and not dry_run:
                repo.enqueue_missing(c, n.missing, source_id, sid)
    if rows and c and not dry_run:
        repo.upsert_normalized(c, rows)


def run(c, *, only_watch_id: int | None = None, dry_run: bool = False, headed: bool = False, user_id: str | None = None) -> Counts:
    counts = Counts()
    d = dictionary.from_db(c)
    watches = repo.my_watch_categories(c)
    if only_watch_id:
        watches = [w for w in watches if w["watch_id"] == only_watch_id]
    user_sources = repo.my_user_sources(c)
    # 소스별로 묶어 브라우저를 한 번만 연다
    by_source: dict[str, list[dict]] = {}
    for w in watches:
        if w["source_id"] and user_sources.get(w["source_id"], {}).get("enabled", True):
            by_source.setdefault(w["source_id"], []).append(w)
    for source_id, ws in by_source.items():
        us = user_sources.get(source_id) or {}
        cap = int(us.get("daily_cap") or 300)
        used = 0
        blocked_streak = 0
        try:
            with make_adapter(ws[0]["adapter_key"], us, headed=headed) as ad:
                for w in ws:
                    counts.categories += 1
                    category = d.categories.get(w["canonical_category_id"]) if w["canonical_category_id"] else None
                    ruleset = repo.active_ruleset(c, source_id, w["canonical_category_id"])
                    for p, items in ad.iter_pages(w["url"], int(w["max_pages"] or 1)):
                        counts.pages += 1
                        counts.listed += len(items)
                        used += 1
                        id_map = {} if dry_run else repo.upsert_source_items(c, items)
                        if dry_run:
                            id_map = {li.item_id: i for i, li in enumerate(items, 1)}
                        counts.upserted += len(id_map)
                        normalize_batch(c, items, id_map, category, d, ruleset=ruleset, extra_keywords=w["extra_keywords_ko"],
                                        source_id=source_id, dry_run=dry_run, counts=counts)
                        if used >= cap:
                            counts.errors.append(f"{source_id}: 하루 요청 상한 {cap} 도달")
                            break
                    if used >= cap:
                        break
        except Blocked as e:
            counts.blocked += 1
            blocked_streak += 1
            counts.errors.append(f"{source_id}: {e}")
        except Exception as e:
            counts.errors.append(f"{source_id}: {type(e).__name__}: {e}")
            counts.errors.append(traceback.format_exc()[-600:])
    return counts


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, help="user_watch_categories.id 하나만")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-lock", action="store_true", help="배치 잠금 없이 (수동 실행)")
    a = ap.parse_args(argv)

    from app.db import current_user_id, pc_name, user_client

    c = user_client()
    uid = current_user_id(c)
    today = date.today()
    if not a.no_lock and not a.dry_run and not repo.acquire_lock(c, today, "collect", pc_name()):
        print("다른 PC 가 오늘 수집 잠금을 가지고 있습니다 (--no-lock 으로 강제 가능)")
        return 3
    counts = run(c, only_watch_id=a.watch, dry_run=a.dry_run, headed=a.headed, user_id=uid)
    print(f"카테고리 {counts.categories} · 페이지 {counts.pages} · 카드 {counts.listed} · upsert {counts.upserted} · 정규화 {counts.normalized} "
          f"(공용 제외 {counts.excluded} · 확인 대기 {counts.pending}) · 차단 {counts.blocked}")
    for e in counts.errors:
        print("  !", e)
    if not a.dry_run:
        repo.log_run(c, uid, "collect", today, counts.as_dict(), pc_name=pc_name(), error=(counts.errors[0] if counts.errors else None))
    return 0 if not counts.errors else 1


if __name__ == "__main__":
    sys.exit(main())
