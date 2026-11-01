"""첫 계정 만들기 (service_role 키 필요 · 1회).

  python scripts/bootstrap_admin.py --email you@example.com

비밀번호는 프롬프트로 두 번 받는다(인자·환경변수로 받지 않는다). 001 마이그레이션의 트리거가
첫 계정을 profiles.role = 'admin' 으로 만든다. 그 뒤 개인 배송 프로필 2개(템플릿)를 넣는다.
이미 있는 이메일이면 계정 생성은 건너뛰고 배송 프로필만 보충한다.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import service_client  # noqa: E402

TEMPLATES = ROOT / "supabase" / "seed" / "shipping_profile_templates.json"


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--display-name", default=None)
    a = ap.parse_args(argv)

    c = service_client()
    print(f"환경 {settings.app_env} · {settings.supabase_url}")

    # 이미 있는지
    existing = None
    page = c.auth.admin.list_users()
    for u in page or []:
        if (u.email or "").lower() == a.email.lower():
            existing = u
            break
    if existing:
        uid = existing.id
        print(f"계정이 이미 있습니다: {a.email} ({uid})")
    else:
        pw = getpass.getpass("새 비밀번호: ")
        pw2 = getpass.getpass("다시 입력: ")
        if pw != pw2 or len(pw) < 8:
            print("비밀번호가 다르거나 8자 미만입니다")
            return 1
        resp = c.auth.admin.create_user(
            {"email": a.email, "password": pw, "email_confirm": True,
             "user_metadata": {"display_name": a.display_name or a.email.split("@")[0]}}
        )
        uid = resp.user.id
        print(f"계정 생성: {a.email} ({uid})")

    prof = c.table("profiles").select("role").eq("user_id", uid).execute().data
    print(f"profiles.role = {prof[0]['role'] if prof else '(없음 — 001 트리거가 적용됐는지 확인)'}")

    have = c.table("shipping_profiles").select("id").eq("user_id", uid).execute().data
    if have:
        print(f"배송 프로필 {len(have)}개 있음 (건너뜀)")
    else:
        rows = [{"user_id": uid, **t} for t in json.loads(TEMPLATES.read_text(encoding="utf-8"))]
        c.table("shipping_profiles").insert(rows).execute()
        print(f"배송 프로필 {len(rows)}개 생성 (템플릿)")
    print("다음: python -m app.auth login --email", a.email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
