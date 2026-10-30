"""OpenAI 어댑터 자리. 초기 운영은 제공자 1개(Claude)로 시작하고, 이 파일은 같은 인터페이스로 채운다."""
from __future__ import annotations

from .base import LLM, LLMNotConfigured


class OpenAILLM(LLM):
    provider = "openai"

    def __init__(self, model: str | None = None):
        raise LLMNotConfigured("OpenAI 어댑터는 아직 구현 전입니다. LLM_PROVIDER=claude 로 설정하세요.")
