"""로그인·세션 (Supabase Auth).

  python -m app.auth login [--email you@example.com]   # 비밀번호는 프롬프트로만 받는다
  python -m app.auth status                            # 누구로 · 어느 환경 · 설정이 DB 에서 오는지
  python -m app.auth logout

세션 토큰은 PC 로컬 ~/.auto-store/session.<env>.json 에 남는다 (DESIGN 4.1 "PC 에 남는 것").
dev 와 prd 는 다른 Supabase 프로젝트라 세션 파일도 환경별로 따로 둔다.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

from app.config import settings

SESSION_DIR = Path(os.getenv("AUTO_STORE_HOME") or (Path.home() / ".auto-store"))
SESSION_FILE = SESSION_DIR / f"session.{settings.app_env}.json"


def save_session(session, *, email: str | None = None) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_at": getattr(session, "expires_at", None),
        "email": email or (session.user.email if getattr(session, "user", None) else None),
        "supabase_url": settings.supabase_url,
        "saved_at": int(time.time()),
    }
    SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SESSION_FILE, 0o600)
    except Exception:
        pass


def load_session() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        d = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    # 다른 프로젝트(dev ↔ prd 전환 등)의 세션이면 쓰지 않는다
    if d.get("supabase_url") and d["supabase_url"] != settings.supabase_url:
        return None
    return d if d.get("access_token") and d.get("refresh_token") else None


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def login(email: str | None = None, password: str | None = None) -> dict:
    from app.db import anon_client

    email = email or os.getenv("APP_LOGIN_EMAIL") or input("이메일: ").strip()
    password = password or getpass.getpass("비밀번호: ")
    c = anon_client()
    resp = c.auth.sign_in_with_password({"email": email, "password": password})
    if not resp.session:
        raise RuntimeError("로그인 실패: 세션이 없습니다")
    save_session(resp.session, email=email)
    return {"email": email, "user_id": resp.user.id if resp.user else None}


def status() -> str:
    from app.db import current_user_id, user_client
    from app.user_settings import ensure_user_settings

    lines = [f"환경: {settings.app_env}  ·  Supabase: {settings.supabase_url or '(없음)'}", f"세션 파일: {SESSION_FILE}"]
    sess = load_session()
    if not sess:
        lines.append("로그인 상태: 없음 → python -m app.auth login")
        return "\n".join(lines)
    try:
        c = user_client()
        uid = current_user_id(c)
        prof = c.table("profiles").select("display_name, role, telegram_chat_id").eq("user_id", uid).limit(1).execute().data
        p = prof[0] if prof else {}
        lines.append(f"로그인: {sess.get('email')}  ·  user_id {uid}  ·  role {p.get('role', '?')}  ·  이름 {p.get('display_name') or '-'}")
        us, created = ensure_user_settings(c, uid)
        lines.append(f"user_settings: {'방금 .env 기본값으로 생성' if created else '있음'}  ·  목표 마진 {float(us['target_margin_rate']) * 100:.0f}%  ·  하루 카드 {us['daily_candidate_n']}  ·  LLM {us['llm_provider']}/{us['llm_model'] or '(기본)'}")
        dv = c.rpc("current_dict_version").execute().data
        cats = c.table("canonical_categories").select("id", count="exact").limit(1).execute().count
        lines.append(f"공용 사전: dict_version {dv}  ·  표준 카테고리 {cats}개")
    except Exception as e:
        lines.append(f"조회 실패: {type(e).__name__}: {e}")
    return "\n".join(lines)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Supabase 로그인 · 세션")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login")
    lg.add_argument("--email")
    sub.add_parser("status")
    sub.add_parser("logout")
    a = ap.parse_args(argv)
    if a.cmd == "login":
        r = login(a.email)
        print(f"로그인 완료: {r['email']}  (환경 {settings.app_env}) → 세션 저장 {SESSION_FILE}")
        print(status())
        return 0
    if a.cmd == "status":
        print(status())
        return 0
    if a.cmd == "logout":
        clear_session()
        print("세션 삭제됨")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
