"""Supabase 클라이언트.

- anon_client(): anon 키만. 로그인 전(sign_in) 과 공개 호출용.
- user_client(): anon 키 + 저장된 로그인 세션(JWT). 워커·CLI·관리자 웹이 쓰는 기본. RLS 가 그대로 적용된다.
- service_client(): service_role 키. 마이그레이션·시드·계정 부트스트랩 스크립트 전용 (scripts/). 앱 코드에서 쓰지 않는다.
"""
from __future__ import annotations

import os
import socket

from supabase import Client, create_client

from app.config import settings


class NotLoggedIn(RuntimeError):
    pass


def pc_name() -> str:
    return os.getenv("AUTO_STORE_PC_NAME") or socket.gethostname()


def _require(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"{name} 가 비어 있습니다. .env.{settings.app_env} 를 확인하세요 (python -m app.config)")
    return value


def anon_client() -> Client:
    return create_client(_require("SUPABASE_URL", settings.supabase_url), _require("SUPABASE_ANON_KEY", settings.supabase_anon_key))


def service_client() -> Client:
    key = os.getenv("SUPABASE_SERVICE_KEY") or ""
    return create_client(_require("SUPABASE_URL", settings.supabase_url), _require("SUPABASE_SERVICE_KEY", key))


def user_client() -> Client:
    """저장된 세션으로 로그인된 클라이언트. 토큰이 만료됐으면 refresh 하고 세션 파일을 갱신한다."""
    from app import auth

    sess = auth.load_session()
    if not sess:
        raise NotLoggedIn(f"로그인이 필요합니다: python -m app.auth login   (환경 {settings.app_env})")
    c = anon_client()
    try:
        resp = c.auth.set_session(sess["access_token"], sess["refresh_token"])
    except Exception as e:
        raise NotLoggedIn(f"세션 복원 실패({type(e).__name__}). 다시 로그인하세요: python -m app.auth login") from e
    if resp and resp.session:
        auth.save_session(resp.session, email=sess.get("email"))
    return c


def current_user_id(c: Client) -> str:
    u = c.auth.get_user()
    if not u or not u.user:
        raise NotLoggedIn("사용자 정보를 읽지 못했습니다. 다시 로그인하세요")
    return u.user.id
