"""supabase/migrations/*.sql 을 순서대로 적용한다 (schema_migrations 테이블로 적용 기록).

  python scripts/migrate.py            # SUPABASE_DB_URL 로 접속해 미적용 파일만 실행
  python scripts/migrate.py --print    # 전부 이어붙여 출력 → Supabase SQL Editor 에 붙여 넣을 때
  python scripts/migrate.py --status   # 적용 여부만

SUPABASE_DB_URL 은 Supabase 대시보드 → Project Settings → Database → Connection string (URI, Direct 또는 Session pooler).
.env.{APP_ENV} 에 넣는다. 이 스크립트는 DB 비밀번호가 든 URL 을 쓰므로 PC 에서 작업이 끝나면 지워도 된다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402  (.env.{APP_ENV} 로드)

MIG_DIR = ROOT / "supabase" / "migrations"


def files() -> list[Path]:
    return sorted(p for p in MIG_DIR.glob("*.sql") if p.name[:3].isdigit())


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", help="SQL 을 이어붙여 출력만")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)

    fs = files()
    if a.print:
        for p in fs:
            print(f"\n-- ===== {p.name} =====\n")
            print(p.read_text(encoding="utf-8"))
        return 0

    url = os.getenv("SUPABASE_DB_URL") or ""
    if not url:
        print(f"SUPABASE_DB_URL 이 없습니다 (.env.{settings.app_env}). 대신 `--print` 로 출력해 SQL Editor 에 붙여 넣어도 됩니다.")
        return 2
    import psycopg

    print(f"환경 {settings.app_env} · 마이그레이션 {len(fs)}개 · DB {url.split('@')[-1].split('/')[0] if '@' in url else '(url)'}")
    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("create table if not exists public.schema_migrations (filename text primary key, applied_at timestamptz not null default now())")
            # service_role 만 쓰는 기록 테이블. RLS 를 켜 두면 anon/authenticated 로는 보이지 않는다 (정책 없음 = 거부)
            cur.execute("alter table public.schema_migrations enable row level security")
            conn.commit()
            cur.execute("select filename from public.schema_migrations")
            done = {r[0] for r in cur.fetchall()}
        for p in fs:
            if p.name in done:
                print(f"  = {p.name} (적용됨)")
                continue
            if a.status:
                print(f"  - {p.name} (미적용)")
                continue
            sql = p.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("insert into public.schema_migrations (filename) values (%s)", (p.name,))
                conn.commit()
                print(f"  + {p.name} 적용")
            except Exception as e:
                conn.rollback()
                print(f"  ! {p.name} 실패: {type(e).__name__}: {e}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
