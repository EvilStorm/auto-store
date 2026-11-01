from pydantic import BaseModel

from app import ai_cache
from app.adapters.llm.base import LLM, ImageRef, UsageRecord


class Out(BaseModel):
    answer: str


class FakeLLM(LLM):
    provider = "fake"
    model = "fake-1"

    def __init__(self):
        super().__init__()
        self.calls = 0

    def _call(self, prompt, schema, *, system, images, effort):
        self.calls += 1
        return schema(answer=f"r{self.calls}"), UsageRecord(self.provider, self.model, "", 10, 5, 1.5)


def test_same_input_hits_cache_across_instances():
    mem = ai_cache.MemoryCache()
    ai_cache.set_backend(mem)
    try:
        a = FakeLLM()
        r1 = a.complete_json("hello", Out, purpose="logo_check", images=[ImageRef("http://x/1.jpg", phash="abc")])
        b = FakeLLM()  # 다른 요청자(계정) 역할
        r2 = b.complete_json("hello", Out, purpose="logo_check", images=[ImageRef("http://cdn.other/zzz.jpg", phash="abc")])
        assert r1.answer == r2.answer == "r1"
        assert a.calls == 1 and b.calls == 0
        assert mem.hits == 1
        assert b.cache_hits() == 1 and b.total_cost_krw() == 0.0
    finally:
        ai_cache.set_backend(ai_cache.NullCache())


def test_different_image_or_purpose_misses():
    mem = ai_cache.MemoryCache()
    ai_cache.set_backend(mem)
    try:
        a = FakeLLM()
        a.complete_json("hello", Out, purpose="logo_check", images=[ImageRef("u", phash="abc")])
        a.complete_json("hello", Out, purpose="logo_check", images=[ImageRef("u", phash="def")])   # 사진 바뀜
        a.complete_json("hello", Out, purpose="match")                                            # 다른 용도
        assert a.calls == 3 and mem.hits == 0
    finally:
        ai_cache.set_backend(ai_cache.NullCache())


def test_null_cache_always_calls():
    a = FakeLLM()
    a.complete_json("x", Out)
    a.complete_json("x", Out)
    assert a.calls == 2


def test_hash_ignores_whitespace_only_changes():
    k1 = ai_cache.input_hash("p@v1", "m", "a  b\nc", "s", [], "Out")
    k2 = ai_cache.input_hash("p@v1", "m", "a b c", "s", [], "Out")
    assert k1 == k2
