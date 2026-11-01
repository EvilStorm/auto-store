"""텔레그램 Bot API (httpx 직접 호출). 인라인 버튼 · 콜백 · 롱폴링. 토큰은 개인 시크릿(user_secrets) 또는 .env."""
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class Bot:
    token: str
    chat_id: str

    def _call(self, method: str, **params):
        r = httpx.post(API.format(token=self.token, method=method), json=params, timeout=30.0)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method}: {data.get('description')}")
        return data["result"]

    def send_text(self, text: str, *, buttons: list[list[tuple[str, str]]] | None = None, disable_preview: bool = True) -> int:
        kw = {"chat_id": self.chat_id, "text": text[:4000], "disable_web_page_preview": disable_preview}
        if buttons:
            kw["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
        return self._call("sendMessage", **kw)["message_id"]

    def send_photo(self, photo_url: str, caption: str, *, buttons: list[list[tuple[str, str]]] | None = None) -> int:
        kw = {"chat_id": self.chat_id, "photo": photo_url, "caption": caption[:1000]}
        if buttons:
            kw["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
        try:
            return self._call("sendPhoto", **kw)["message_id"]
        except Exception:
            # 이미지 URL 을 텔레그램이 못 가져오면 텍스트로
            return self.send_text(caption, buttons=buttons)

    def edit_buttons(self, message_id: int, buttons: list[list[tuple[str, str]]] | None) -> None:
        markup = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in (buttons or [])]}
        try:
            self._call("editMessageReplyMarkup", chat_id=self.chat_id, message_id=message_id, reply_markup=markup)
        except Exception:
            pass

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call("answerCallbackQuery", callback_query_id=callback_id, text=text[:200])
        except Exception:
            pass

    def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        kw = {"timeout": timeout, "allowed_updates": ["callback_query", "message"]}
        if offset is not None:
            kw["offset"] = offset
        r = httpx.post(API.format(token=self.token, method="getUpdates"), json=kw, timeout=timeout + 10)
        data = r.json()
        if not data.get("ok"):
            if data.get("error_code") == 409:
                raise RuntimeError("다른 프로세스가 같은 봇을 폴링 중 (409)")
            raise RuntimeError(f"telegram getUpdates: {data.get('description')}")
        return data["result"]

    def me(self) -> dict:
        return self._call("getMe")


def callback_data(kind: str, cid: int, action: str) -> str:
    return f"{kind}:{cid}:{action}"


def parse_callback(data: str) -> tuple[str, int, str] | None:
    try:
        kind, cid, action = data.split(":", 2)
        return kind, int(cid), action
    except Exception:
        return None


def bot_from(client=None) -> Bot:
    """토큰 · chat_id: user_secrets(telegram_bot_token) · profiles.telegram_chat_id → 없으면 .env."""
    from app.config import settings

    token, chat_id = settings.telegram_bot_token, settings.telegram_chat_id
    if client is not None:
        try:
            rows = client.table("user_secrets").select("value").eq("name", "telegram_bot_token").limit(1).execute().data
            if rows:
                token = rows[0]["value"]
            prof = client.table("profiles").select("telegram_chat_id").limit(1).execute().data
            if prof and prof[0].get("telegram_chat_id"):
                chat_id = prof[0]["telegram_chat_id"]
        except Exception:
            pass
    if not token or not chat_id:
        raise RuntimeError("텔레그램 봇 토큰 · chat_id 가 없습니다 (user_secrets/profiles 또는 .env TELEGRAM_*)")
    return Bot(token, str(chat_id))


__all__ = ["Bot", "bot_from", "callback_data", "parse_callback", "json"]
