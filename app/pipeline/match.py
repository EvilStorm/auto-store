"""③ 매칭: 네이버 쇼핑 검색 → LLM 이 정확/유사/무관 판정 + 근거 + 카테고리 추천.

데이터랩 수요 신호와 동일 이미지 판매자 수는 아직 미연결(None). 카드에는 '미연결'로 표시한다.
"""
from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.adapters import naver_shopping as naver
from app.adapters.llm.base import LLM, ImageRef
from app.config import settings
from app.pipeline.extract import Normalized, RawDetail


class ItemJudgement(BaseModel):
    index: int
    relation: Literal["exact", "similar", "unrelated"]
    reason: str = Field(description="한 줄 근거")


class MatchJudgement(BaseModel):
    items: list[ItemJudgement]
    overall_reason: str = Field(description="전체 판정 근거 한 줄 (핵심 속성 일치 여부)")
    recommended_naver_category: Optional[str] = Field(default=None, description="정확 매칭 상품들의 네이버 카테고리 경로")


class MatchResult(BaseModel):
    queries: list[str]
    total_results: int = 0
    exact: list[dict] = Field(default_factory=list)
    similar: list[dict] = Field(default_factory=list)
    exact_count: int = 0
    similar_count: int = 0
    domestic_price_krw: Optional[int] = None
    price_basis: str = ""
    basis_match_type: Optional[str] = None  # exact | similar
    naver_category: Optional[str] = None
    reason: str = ""
    skipped_reason: Optional[str] = None
    demand_trend_pct: Optional[float] = None  # 데이터랩 미연결
    same_image_sellers: Optional[int] = None  # 미연결


SYSTEM_MATCH = (
    "너는 해외 소스 상품과 네이버 쇼핑 검색 결과를 비교해 같은 상품인지 판정한다. "
    "exact = 동일 상품(같은 공산품으로 보임, 용량·형태·재질·구성 일치), similar = 같은 종류의 비슷한 상품, unrelated = 다른 종류. "
    "이미지가 있으면 이미지 일치를 가장 중시하고, 가격은 판정에 쓰지 않는다."
)


def _basis_price(prices: list[int]) -> int:
    if not prices:
        return 0
    b = settings.price_basis
    if b == "median":
        return int(median(prices))
    if b == "min":
        return int(min(prices))
    return int(mean(prices))


def run_match(llm: LLM, raw: RawDetail, norm: Normalized, main_image: str) -> MatchResult:
    res = MatchResult(queries=norm.search_queries)
    if not naver.available():
        res.skipped_reason = "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음 → 매칭 생략"
        return res

    pool: dict[str, naver.NaverItem] = {}
    total = 0
    for q in norm.search_queries[:3]:
        r = naver.search(q, display=settings.naver_top_n)
        if not r:
            continue
        total = max(total, r.total)
        for it in r.items:
            pool.setdefault(it.product_id or it.link, it)
    items = list(pool.values())[: settings.naver_top_n * 2]
    res.total_results = total
    if not items:
        res.skipped_reason = "네이버 검색 결과 없음"
        return res

    lines = []
    images = [ImageRef(main_image, "소스 상품 대표 이미지")] if main_image else []
    for i, it in enumerate(items):
        lines.append(f"[{i}] {it.title} | {it.lprice:,}원 | {it.mall} | {it.category} | 브랜드:{it.brand or '-'}")
        if i < 6 and it.image:
            images.append(ImageRef(it.image, f"후보 [{i}] 이미지"))
    prompt = (
        f"소스 상품: {norm.title_ko} (원문: {raw.title_raw})\n핵심 속성: {', '.join(norm.key_attributes)}\n"
        f"옵션: {[o.name for o in raw.options][:10]}\n\n네이버 검색 결과:\n" + "\n".join(lines)
    )
    j = llm.complete_json(prompt, MatchJudgement, system=SYSTEM_MATCH, images=images, purpose="match", effort="low")

    rel = {x.index: x for x in j.items}
    for i, it in enumerate(items):
        jj = rel.get(i)
        if not jj:
            continue
        row = {
            "title": it.title,
            "price": it.lprice,
            "mall": it.mall,
            "link": it.link,
            "category": it.category,
            "reason": jj.reason,
        }
        if jj.relation == "exact":
            res.exact.append(row)
        elif jj.relation == "similar":
            res.similar.append(row)

    res.exact_count = len(res.exact)
    res.similar_count = len(res.similar)
    res.reason = j.overall_reason
    res.price_basis = settings.price_basis

    if res.exact:
        res.domestic_price_krw = _basis_price([r["price"] for r in res.exact if r["price"]])
        res.basis_match_type = "exact"
    elif res.similar:
        res.domestic_price_krw = _basis_price([r["price"] for r in res.similar if r["price"]])
        res.basis_match_type = "similar"

    cats = Counter(r["category"] for r in res.exact if r["category"]) or Counter(r["category"] for r in res.similar if r["category"])
    res.naver_category = j.recommended_naver_category or (cats.most_common(1)[0][0] if cats else None)
    return res
