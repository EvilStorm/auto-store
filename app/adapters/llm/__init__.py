"""LLM 제공자 선택. LLM_PROVIDER = claude | gemini | openai"""
from __future__ import annotations

from app.config import settings

from .base import LLM, LLMNotConfigured


def get_llm() -> LLM:
    p = (settings.llm_provider or "claude").lower()
    if p == "claude":
        from .claude import ClaudeLLM

        return ClaudeLLM(model=settings.llm_model or None)
    if p == "gemini":
        from .gemini import GeminiLLM

        return GeminiLLM(model=settings.llm_model or None)
    if p == "openai":
        from .openai_ import OpenAILLM

        return OpenAILLM(model=settings.llm_model or None)
    raise LLMNotConfigured(f"알 수 없는 LLM_PROVIDER: {p}")


__all__ = ["get_llm", "LLM", "LLMNotConfigured"]
