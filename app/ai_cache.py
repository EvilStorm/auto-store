"""AI 결과 캐시 (DESIGN.md 3.6). 키 = (purpose@버전, model, 입력 해시). 같은 키면 호출하지 않는다.

백엔드 세 가지: SupabaseCache(공용 ai_results), MemoryCache(테스트), NullCache(캐시 끔).
이미지는 URL 이 아니라 pHash 로 키에 넣는다 — 호출 측이 ImageRef.phash 를 채워 주면 그걸 쓰고, 없으면 URL 로 대체한다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol


def input_hash(purpose: str, model: str, prompt: str, system: str, image_keys: list[str], schema_name: str) -> str:
    payload = json.dumps(
        {"p": purpose, "m": model, "s": " ".join(system.split()), "u": " ".join(prompt.split()), "i": image_keys, "schema": schema_name},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CacheBackend(Protocol):
    def get(self, purpose: str, model: str, key: str) -> dict | None: ...
    def put(self, purpose: str, model: str, key: str, output: dict, est_cost_krw: float) -> None: ...


class NullCache:
    def get(self, purpose, model, key):
        return None

    def put(self, purpose, model, key, output, est_cost_krw):
        return None


class MemoryCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], dict] = {}
        self.hits = 0

    def get(self, purpose, model, key):
        v = self.store.get((purpose, model, key))
        if v is not None:
            self.hits += 1
        return v

    def put(self, purpose, model, key, output, est_cost_krw):
        self.store[(purpose, model, key)] = output


class SupabaseCache:
    """공용 ai_results. 적중은 RPC ai_cache_hit 로 hits+1 과 함께 읽는다."""

    def __init__(self, client) -> None:
        self.c = client

    def get(self, purpose, model, key):
        try:
            data = self.c.rpc("ai_cache_hit", {"p_purpose": purpose, "p_model": model, "p_input_hash": key}).execute().data
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def put(self, purpose, model, key, output: dict[str, Any], est_cost_krw: float):
        try:
            self.c.table("ai_results").upsert(
                {"purpose": purpose, "model": model, "input_hash": key, "output_json": output, "est_cost_krw": round(est_cost_krw, 2)},
                on_conflict="purpose,model,input_hash",
            ).execute()
        except Exception:
            pass  # 캐시 실패는 결과에 영향 없음


_backend: CacheBackend = NullCache()


def set_backend(b: CacheBackend) -> None:
    global _backend
    _backend = b


def backend() -> CacheBackend:
    return _backend
