"""모든 LLM 제공자가 지키는 공통 인터페이스.

complete_json(prompt, schema, images) 하나만 있으면 파이프라인 전체가 돈다.
v3: complete_json 은 먼저 AI 결과 캐시(app.ai_cache)를 본다. 같은 (purpose, model, 입력 해시)면 호출 없이 돌려준다.
제공자 어댑터는 _call() 만 구현한다. 비용 추정은 UsageRecord 로 돌려주고 billing 에서 합산한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Type, TypeVar

from pydantic import BaseModel

from app import ai_cache

T = TypeVar("T", bound=BaseModel)

PROMPT_VERSION = "v1"  # 프롬프트 템플릿이 바뀌면 올린다 → 캐시 키가 바뀐다


class LLMNotConfigured(RuntimeError):
    pass


@dataclass
class UsageRecord:
    provider: str
    model: str
    purpose: str
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_krw: float = 0.0
    cache_hit: bool = False


@dataclass
class ImageRef:
    """URL 이미지. phash 가 있으면 캐시 키에 URL 대신 쓴다 (같은 사진 = 같은 키)."""

    url: str
    label: str = ""
    phash: str | None = None

    def cache_key(self) -> str:
        return f"phash:{self.phash}" if self.phash else f"url:{self.url}"


class LLM:
    provider: str = "base"
    model: str = ""

    def __init__(self) -> None:
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
        use_cache: bool = True,
    ) -> T:
        purpose_v = f"{purpose}@{PROMPT_VERSION}"
        key = ai_cache.input_hash(purpose_v, self.model, prompt, system, [im.cache_key() for im in images], schema.__name__)
        cache = ai_cache.backend()
        if use_cache:
            hit = cache.get(purpose_v, self.model, key)
            if hit is not None:
                self.usage.append(UsageRecord(self.provider, self.model, purpose, cache_hit=True))
                return schema.model_validate(hit)
        result, usage = self._call(prompt, schema, system=system, images=images, effort=effort)
        usage.purpose = purpose
        self.usage.append(usage)
        if use_cache:
            cache.put(purpose_v, self.model, key, result.model_dump(mode="json"), usage.est_cost_krw)
        return result

    def _call(self, prompt: str, schema: Type[T], *, system: str, images: Sequence[ImageRef], effort: str) -> tuple[T, UsageRecord]:
        raise NotImplementedError

    def total_cost_krw(self) -> float:
        return sum(u.est_cost_krw for u in self.usage)

    def cache_hits(self) -> int:
        return sum(1 for u in self.usage if u.cache_hit)
