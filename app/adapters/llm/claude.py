"""Claude 어댑터. 구조화 출력은 messages.parse(output_format=PydanticModel) 로 받는다."""
from __future__ import annotations

from typing import Sequence, Type, TypeVar

import anthropic
from pydantic import BaseModel

from app.config import settings

from .base import LLM, ImageRef, LLMNotConfigured, UsageRecord

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"

# USD per 1M tokens (입력, 출력). 비용은 추정치이며 청구액이 아니다.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
USD_KRW_FOR_ESTIMATE = 1400.0


class ClaudeLLM(LLM):
    provider = "claude"

    def __init__(self, model: str | None = None):
        if not settings.anthropic_api_key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY 가 없습니다. .env 에 넣어주세요.")
        self.model = model or DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)
        self.usage: list[UsageRecord] = []

    def complete_json(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system: str = "",
        images: Sequence[ImageRef] = (),
        purpose: str = "generic",
        effort: str = "low",
    ) -> T:
        content: list[dict] = []
        for im in images:
            if im.label:
                content.append({"type": "text", "text": f"[이미지: {im.label}]"})
            content.append({"type": "image", "source": {"type": "url", "url": im.url}})
        content.append({"type": "text", "text": prompt})

        kwargs = dict(
            model=self.model,
            max_tokens=8000,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": effort},
        )
        if system:
            kwargs["system"] = system

        try:
            resp = self.client.messages.parse(**kwargs)
        except anthropic.BadRequestError as e:
            # 이미지 URL 을 못 가져오는 경우(핫링크 차단 등) 이미지 없이 한 번 더 시도
            if images and "image" in str(e).lower():
                kwargs["messages"] = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
                resp = self.client.messages.parse(**kwargs)
            else:
                raise

        if resp.stop_reason == "refusal":
            raise RuntimeError(f"LLM 이 응답을 거부했습니다: {getattr(resp, 'stop_details', None)}")

        u = resp.usage
        pin, pout = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        cost_usd = (u.input_tokens / 1e6) * pin + (u.output_tokens / 1e6) * pout
        self.usage.append(
            UsageRecord(
                provider=self.provider,
                model=self.model,
                purpose=purpose,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                est_cost_krw=round(cost_usd * USD_KRW_FOR_ESTIMATE, 1),
            )
        )
        parsed = resp.parsed_output
        if parsed is None:
            raise RuntimeError("LLM 구조화 출력 파싱 실패")
        return parsed
