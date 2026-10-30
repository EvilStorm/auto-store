"""② 정규화의 즉시 분석 버전: 페이지 스냅샷 → 상품 정보 추출 → 한국어 정규화·요건·브랜드 판정.

LLM 호출 2번: (1) 원시 추출  (2) 정규화·판정. 둘 다 구조화 출력.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.adapters.llm.base import LLM, ImageRef
from app.sources.fetch import PageSnapshot


class PriceTier(BaseModel):
    min_qty: int = Field(description="이 단가가 적용되는 최소 수량")
    unit_price: float = Field(description="해당 구간 단가(소스 통화)")


class OptionInfo(BaseModel):
    name: str
    price: Optional[float] = None
    sold_out: bool = False


class RawDetail(BaseModel):
    """페이지에서 보이는 그대로 뽑은 값. 추측하지 말고 없으면 null."""

    title_raw: str
    lang: Literal["zh", "ja", "en", "ko", "other"]
    currency: Literal["CNY", "JPY", "USD", "KRW", "unknown"]
    price_tiers: list[PriceTier] = Field(description="수량 구간별 단가. 단일가면 1개")
    moq: int = Field(description="최소 주문 수량. 모르면 1")
    options: list[OptionInfo] = Field(default_factory=list)
    weight_g: Optional[float] = Field(default=None, description="상품 또는 포장 무게(g). 없으면 null")
    material_raw: Optional[str] = Field(default=None, description="재질 원문")
    category_raw: Optional[str] = Field(default=None, description="빵부스러기/분류 표기 원문")
    brand_text: Optional[str] = Field(default=None, description="제목·속성에 보이는 브랜드명")
    seller_or_store: Optional[str] = None
    sold_out: bool = False
    is_product_page: bool = Field(description="상품 상세 페이지가 맞는지. 로그인/캡차/목록 페이지면 false")
    page_problem: Optional[str] = Field(default=None, description="상품 페이지가 아니거나 정보가 가려진 이유")


class Normalized(BaseModel):
    title_ko: str = Field(description="한국 소비자용 상품명 초안, 50자 이내, 브랜드명 제외")
    search_queries: list[str] = Field(description="네이버 쇼핑 검색어 2~3개. 짧고 일반적인 한국어. 브랜드·중국 내수 표현 제거")
    material_code: Literal["glass", "ceramic", "battery", "liquid", "magnet", "wood", "stainless", "silicone", "plastic", "fabric", "metal", "paper", "other", "unknown"]
    item_type: Literal["general", "electronics", "kids", "food", "cosmetics", "medical", "other"]
    requirement_status: Literal["pass", "required", "excluded"] = Field(
        description="통과 / 요건 필요(전기용품·전파·어린이제품 KC 등) / 제외(식품·화장품·의약외품·목록통관 배제)"
    )
    requirement_reason: str
    brand_detected: bool = Field(description="제목·속성·이미지에 타사 브랜드/캐릭터 로고나 상표가 보이는지")
    brand_reason: str
    key_attributes: list[str] = Field(description="매칭에 쓸 핵심 속성 3~6개 (용량, 크기, 재질, 형태 등)")


SYSTEM_EXTRACT = (
    "너는 해외 도매 상품 페이지에서 구조화 정보를 뽑는 추출기다. 페이지 텍스트와 이미지에 실제로 보이는 값만 쓰고, "
    "없으면 null 로 둔다. 가격 구간은 '수량 범위 → 단가' 쌍으로 정리한다. 통화는 반드시 페이지에 보이는 기호를 따른다: "
    "₩ 는 KRW, ¥/￥ 는 중국 사이트면 CNY · 일본 사이트면 JPY, $ 는 USD. (1688 해외 사이트와 알리익스프레스 한국 페이지는 ₩ 원화로 표시되는 경우가 많다.)"
)

SYSTEM_NORMALIZE = (
    "너는 한국 구매대행 셀러의 상품 검수자다. 원문 상품 정보를 한국어로 정규화하고, 재질 코드·품목 유형·수입 요건·브랜드 노출 여부를 판정한다. "
    "요건 규칙: 전원/배터리/무선 통신이 있는 전기·전자제품은 required(KC·전파인증), 13세 이하 아동용은 required(어린이제품 KC), "
    "식품·건강기능식품·화장품·의약외품·의료기기는 excluded, 그 외 일반 생활용품은 pass. "
    "브랜드: 타사 로고·캐릭터(디즈니, 산리오 등)·브랜드명이 상품 자체에 보이면 brand_detected=true. 판매자 상호만 있는 경우는 false."
)


def extract_raw(llm: LLM, snap: PageSnapshot) -> RawDetail:
    images = [ImageRef(snap.main_image(), "대표 이미지")] if snap.main_image() else []
    prompt = (
        f"URL: {snap.final_url}\n페이지 제목: {snap.title}\n\n"
        f"메타: {snap.metas}\n\n페이지 텍스트(일부):\n{snap.text}\n"
    )
    return llm.complete_json(prompt, RawDetail, system=SYSTEM_EXTRACT, images=images, purpose="extract", effort="low")


def normalize(llm: LLM, raw: RawDetail, snap: PageSnapshot) -> Normalized:
    images = []
    if snap.main_image():
        images.append(ImageRef(snap.main_image(), "대표 이미지"))
    for u in snap.images[1:3]:
        images.append(ImageRef(u, "추가 이미지"))
    prompt = (
        f"원문 상품명: {raw.title_raw}\n언어: {raw.lang}\n재질 원문: {raw.material_raw}\n분류 원문: {raw.category_raw}\n"
        f"브랜드 텍스트: {raw.brand_text}\n옵션: {[o.name for o in raw.options][:20]}\n"
        f"가격 구간: {[(t.min_qty, t.unit_price) for t in raw.price_tiers]} {raw.currency}\n"
    )
    return llm.complete_json(prompt, Normalized, system=SYSTEM_NORMALIZE, images=images, purpose="normalize", effort="low")
