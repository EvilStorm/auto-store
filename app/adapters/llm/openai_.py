"""OpenAI 어댑터. 구조화 출력은 Responses API 의 parse(text_format=PydanticModel) 로 받는다."""
from __future__ import annotations

from typing import Sequence, Type, TypeVar

from pydantic import BaseModel

from app.config import settings

from .base import LLM, ImageRef, LLMNotConfigured, UsageRecord

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gpt-5"

# USD per 1M tokens (입력, 출력). 추정용이며 청구액이 아니다. 모델이 표에 없으면 DEFAULT_MODEL 단가로 계산한다.
PRICES = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
}
USD_KRW_FOR_ESTIMATE = 1400.0

EFFORT_MAP = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


def _supports_reasoning(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


class OpenAILLM(LLM):
    provider = "openai"

    def __init__(self, model: str | None = None):
        super().__init__()
        if not settings.openai_api_key:
            raise LLMNotConfigured("OPENAI_API_KEY 가 없습니다. .env 에 넣어주세요.")
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMNotConfigured("openai 패키지가 없습니다. pip install openai") from e
        self.model = model or DEFAULT_MODEL
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=120.0)

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
                content.append({"type": "input_text", "text": f"[이미지: {im.label}]"})
            content.append({"type": "input_image", "image_url": im.url, "detail": "low"})
        content.append({"type": "input_text", "text": prompt})

        kwargs = dict(
            model=self.model,
            input=[{"role": "user", "content": content}],
            text_format=schema,
        )
        if system:
            kwargs["instructions"] = system
        if _supports_reasoning(self.model):
            kwargs["reasoning"] = {"effort": EFFORT_MAP.get(effort, "low")}

        from openai import BadRequestError

        try:
            resp = self.client.responses.parse(**kwargs)
        except BadRequestError as e:
            # 이미지 URL 을 못 가져오는 경우(핫링크 차단 등) 이미지 없이 한 번 더 시도
            if images and "image" in str(e).lower():
                kwargs["input"] = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
                resp = self.client.responses.parse(**kwargs)
            else:
                raise

        u = resp.usage
        in_t = getattr(u, "input_tokens", 0) or 0
        out_t = getattr(u, "output_tokens", 0) or 0
        pin, pout = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        cost_usd = (in_t / 1e6) * pin + (out_t / 1e6) * pout
        self.usage.append(
            UsageRecord(
                provider=self.provider,
                model=self.model,
                purpose=purpose,
                input_tokens=in_t,
                output_tokens=out_t,
                est_cost_krw=round(cost_usd * USD_KRW_FOR_ESTIMATE, 1),
            )
        )
        parsed = resp.output_parsed
        if parsed is None:
            refusal = next((o for o in getattr(resp, "output", []) if getattr(o, "type", "") == "refusal"), None)
            raise RuntimeError(f"LLM 구조화 출력 파싱 실패{' (거부: ' + str(refusal) + ')' if refusal else ''}")
        return parsed
