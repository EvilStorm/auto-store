"""모든 LLM 제공자가 지키는 공통 인터페이스.

complete_json(prompt, schema, images) 하나만 있으면 파이프라인 전체가 돈다.
비용 추정은 UsageRecord 로 돌려주고 billing 에서 합산한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


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


@dataclass
class ImageRef:
    """URL 이미지. (base64 가 필요한 제공자는 어댑터에서 내려받는다)"""

    url: str
    label: str = ""


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
    ) -> T:
        raise NotImplementedError

    def total_cost_krw(self) -> float:
        return sum(u.est_cost_krw for u in self.usage)
