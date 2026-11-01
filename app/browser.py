"""Playwright 브라우저 실행 공통 헬퍼 — 내장 크로미움이 막힌 PC(회사 정책 · 백신)에서는 설치된 Chrome / Edge 로 자동 폴백.

순서: PLAYWRIGHT_CHANNEL 환경변수가 있으면 그것만 → 없으면 내장 chromium → chrome → msedge.
"Executable doesn't exist" · "spawn …" 류 실행 오류에서만 다음 후보로 넘어가고, 다른 오류는 그대로 올린다.
한 번 성공한 채널은 프로세스 안에서 기억한다 (다음 실행은 바로 그 채널).
"""
from __future__ import annotations

import os
from pathlib import Path

CANDIDATES = ("", "chrome", "msedge")  # "" = 내장 chromium
_LAUNCH_ERRORS = ("executable doesn't exist", "spawn ", "enoent", "eacces", "failed to launch")
_working: str | None = None


def _order() -> list[str]:
    forced = os.getenv("PLAYWRIGHT_CHANNEL")
    if forced is not None and forced != "":
        return [forced]
    if _working is not None:
        return [_working] + [c for c in CANDIDATES if c != _working]
    return list(CANDIDATES)


def _is_launch_error(e: Exception) -> bool:
    m = str(e).lower()
    return any(k in m for k in _LAUNCH_ERRORS)


def _try(fn, **kw):
    global _working
    last: Exception | None = None
    for ch in _order():
        try:
            out = fn(**({**kw, "channel": ch} if ch else kw))
            _working = ch
            return out
        except Exception as e:  # noqa: BLE001
            if not _is_launch_error(e):
                raise
            last = e
    raise RuntimeError(f"브라우저를 실행할 수 없습니다 (내장 chromium · chrome · msedge 모두 실패). 마지막 오류: {last}")


def launch(pw, *, headless: bool = True, **kw):
    """pw.chromium.launch 와 같되 폴백 포함."""
    return _try(lambda **k: pw.chromium.launch(headless=headless, **k), **kw)


def launch_persistent(pw, profile_dir: Path | str, *, headless: bool = True, **kw):
    """pw.chromium.launch_persistent_context 와 같되 폴백 포함. 프로필 폴더는 만들어 둔다.

    자동화 브라우저에서는 알리바바 계열 로그인 캡차가 통과되지 않는 경우가 많다. 이 프로젝트는 캡차를 우회하지 않는다:
    프로필 폴더가 일반 Chrome 의 --user-data-dir 과 호환되므로, 사람이 Playwright 없이 Chrome 을 같은 폴더로 띄워
    직접 로그인해 두면 이후 수집은 그 세션을 그대로 쓴다 (SETUP.md 5-4-1). 로그인 없이도 목록 수집은 대체로 된다.
    """
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    return _try(lambda **k: pw.chromium.launch_persistent_context(str(profile_dir), headless=headless, **k), **kw)


def working_channel() -> str:
    return _working or os.getenv("PLAYWRIGHT_CHANNEL") or "chromium"
