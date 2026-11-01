"""공용 참조 데이터 시드 (supabase/seed/*). service_role 키로 PostgREST upsert — DB URL 불필요.

  python scripts/seed.py            # 전부 upsert (여러 번 실행 안전)
  python scripts/seed.py --only canonical_categories,category_aliases

마지막에 dict_version 을 +1 한다(사전이 바뀌었으니). 배송 프로필 템플릿은 공용 테이블이 아니라
각 계정이 처음 로그인할 때 개인 shipping_profiles 로 복사된다(scripts/bootstrap_admin.py · 관리자 웹).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import service_client  # noqa: E402

SEED = ROOT / "supabase" / "seed"

# (파일, 테이블, 충돌 키, 배열 컬럼)
TABLES = [
    ("sources.csv", "sources", "id", ()),
    ("canonical_categories.csv", "canonical_categories", "id", ("search_keywords_ko",)),
    ("category_aliases.csv", "category_aliases", "term,lang", ()),
    ("attribute_aliases.csv", "attribute_aliases", "kind,term,lang", ()),
    ("brand_blacklist.csv", "brand_blacklist", "name,lang", ()),
    ("title_stopwords.csv", "title_stopwords", "term,lang", ()),
    ("requirements.csv", "requirements", "item_type", ()),
    ("naver_categories.csv", "naver_categories", "cat_id", ()),
]
INT_COLS = {"default_weight_g"}
NUM_COLS = {"confidence"}


def rows_of(path: Path, array_cols: tuple[str, ...]) -> list[dict]:
    out = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            row = {}
            for k, v in r.items():
                if k is None:  # 따옴표 없는 쉼표로 열이 밀린 경우 — 여분 열은 버리고 경고
                    print(f"  ! {path.name}: 열이 밀린 행 (쉼표가 든 값은 따옴표로 감싸세요): {r}")
                    continue
                v = (v or "").strip()
                if k in array_cols:
                    row[k] = [x.strip() for x in v.split("|") if x.strip()]
                elif k in INT_COLS:
                    row[k] = int(v) if v else 0
                elif k in NUM_COLS:
                    row[k] = float(v) if v else None
                else:
                    row[k] = v if v else None
            out.append(row)
    return out


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="쉼표로 테이블 이름")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None

    c = service_client()
    print(f"환경 {settings.app_env} · {settings.supabase_url}")
    for fname, table, on_conflict, arrays in TABLES:
        if only and table not in only:
            continue
        rows = rows_of(SEED / fname, arrays)
        if not rows:
            print(f"  - {table}: 행 없음")
            continue
        # parent_id 가 있는 카테고리는 부모가 먼저 들어가야 FK 가 통과한다 → 부모(parent 없음) 먼저
        if table == "canonical_categories":
            rows.sort(key=lambda r: (r.get("parent_id") is not None, r["id"]))
        res = c.table(table).upsert(rows, on_conflict=on_conflict).execute()
        print(f"  + {table}: {len(res.data or [])}행 upsert")
    if not only:
        dv = c.rpc("bump_dict_version").execute().data
        print(f"dict_version → {dv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
