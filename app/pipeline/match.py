"""③ 매칭: 네이버 통합검색 쇼핑 블록 크롤링 → LLM 이 정확/유사/무관 판정 + 근거 + 카테고리 추천.

쇼핑 검색 API 는 2026-07-31 종료되어 크롤링(app.adapters.naver_crawl)으로 대체했다.
크롤링 카드에는 리뷰 수 · 평점 · 찜 · 가격비교 판매처 수가 함께 있어 경쟁 강도와 리뷰 신호를 같은 호출로 얻는다.
데이터랩 수요 신호는 아직 미연결(None).
"""
from __future__ import annotations

from pathlib import Path
from statistics import mean, median
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.adapters import naver_crawl
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


class MatchResult(BaseModel):
    queries: list[str]
    total_results: int = 0  # 통합검색 쇼핑 블록에서 수집한 카드 수 (API 의 total 과 다름)
    exact: list[dict] = Field(default_factory=list)
    similar: list[dict] = Field(default_factory=list)
    exact_count: int = 0
    similar_count: int = 0
    domestic_price_krw: Optional[int] = None
    price_basis: str = ""
    basis_match_type: Optional[str] = None  # exact | similar
    naver_category: Optional[str] = None  # cat_id (통합검색에서는 경로 대신 id 만 나옴)
    reason: str = ""
    skipped_reason: Optional[str] = None
    demand_trend_pct: Optional[float] = None  # 데이터랩 미연결
    same_image_sellers: Optional[int] = None  # 미연결
    max_seller_count: Optional[int] = None  # 정확 매칭 카탈로그의 가격비교 판매처 수 (최대)
    review_count_avg: Optional[int] = None
    review_count_top: Optional[int] = None
    blocked: bool = False


SYSTEM_MATCH = (
    "너는 해외 소스 상품과 네이버 쇼핑 검색 결과를 비교해 같은 상품인지 판정한다. "
    "exact = 동일 상품(같은 공산품으로 보임: 용량·형태·재질·구성 일치), similar = 같은 종류의 비슷한 상품, unrelated = 다른 종류. "
    "이미지가 있으면 이미지 일치를 가장 중시하고, 가격과 브랜드명은 판정에 쓰지 않는다(노브랜드 소스와 브랜드 국내 상품도 외형이 같으면 exact)."
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


def run_match(llm: LLM, raw: RawDetail, norm: Normalized, main_image: str, *, profile_dir: Path | None = None) -> MatchResult:
    res = MatchResult(queries=norm.search_queries, price_basis=settings.price_basis)
    crawled = naver_crawl.search(norm.search_queries[:3], profile_dir=profile_dir)
    if all(r.blocked for r in crawled):
        res.blocked = True
        res.skipped_reason = "네이버 검색 차단/인증 페이지 → 매칭 생략 (잠시 후 재시도)"
        return res

    pool: dict[str, naver_crawl.CrawledItem] = {}
    for r in crawled:
        for it in r.items:
            if it.is_ad:
                continue
            key = it.nv_mid or it.title
            if key not in pool:
                pool[key] = it
    items = list(pool.values())[: settings.naver_top_n * 2]
    res.total_results = len(items)
    if not items:
        res.skipped_reason = "네이버 쇼핑 결과 없음 (" + "; ".join(r.note for r in crawled if r.note) + ")"
        return res

    lines = []
    images = [ImageRef(main_image, "소스 상품 대표 이미지")] if main_image else []
    for i, it in enumerate(items):
        lines.append(f"[{i}] {it.title} | {it.price:,}원 | {it.mall} | 리뷰 {it.review_count or 0}")
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
            "price": it.price,
            "shipping": it.shipping_krw,
            "mall": it.mall,
            "seller_count": it.seller_count,
            "review_count": it.review_count,
            "rating": it.rating,
            "wish_count": it.wish_count,
            "link": it.link,
            "cat_id": it.cat_id,
            "kind": it.kind,
            "reason": jj.reason,
        }
        if jj.relation == "exact":
            res.exact.append(row)
        elif jj.relation == "similar":
            res.similar.append(row)

    res.exact_count = len(res.exact)
    res.similar_count = len(res.similar)
    res.reason = j.overall_reason

    basis_rows = res.exact or res.similar
    if basis_rows:
        res.domestic_price_krw = _basis_price([r["price"] for r in basis_rows if r["price"]])
        res.basis_match_type = "exact" if res.exact else "similar"
        sellers = [r["seller_count"] for r in basis_rows if r.get("seller_count")]
        res.max_seller_count = max(sellers) if sellers else None
        reviews = [r["review_count"] for r in basis_rows if r.get("review_count")]
        if reviews:
            res.review_count_avg = int(mean(reviews))
            res.review_count_top = max(reviews)
        cats = [r["cat_id"] for r in basis_rows if r.get("cat_id")]
        res.naver_category = max(set(cats), key=cats.count) if cats else None
    return res
