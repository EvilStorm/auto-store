"""네이버 쇼핑 검색 API (공식). 키가 없으면 None 을 돌려주고 파이프라인은 '매칭 생략'으로 진행한다."""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.config import settings

ENDPOINT = "https://openapi.naver.com/v1/search/shop.json"
TAG = re.compile(r"<[^>]+>")


@dataclass
class NaverItem:
    title: str
    lprice: int
    hprice: int
    mall: str
    product_id: str
    product_type: str
    link: str
    image: str
    category: str
    brand: str
    maker: str


@dataclass
class NaverSearchResult:
    query: str
    total: int
    items: list[NaverItem]


def available() -> bool:
    return bool(settings.naver_client_id and settings.naver_client_secret)


def search(query: str, *, display: int = 20, sort: str = "sim") -> NaverSearchResult | None:
    if not available():
        return None
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    with httpx.Client(timeout=15.0) as c:
        r = c.get(ENDPOINT, params={"query": query, "display": display, "sort": sort}, headers=headers)
        r.raise_for_status()
        data = r.json()
    items = []
    for it in data.get("items", []):
        cat = " > ".join(x for x in (it.get("category1"), it.get("category2"), it.get("category3"), it.get("category4")) if x)
        items.append(
            NaverItem(
                title=TAG.sub("", it.get("title", "")),
                lprice=int(it.get("lprice") or 0),
                hprice=int(it.get("hprice") or 0),
                mall=it.get("mallName", ""),
                product_id=str(it.get("productId", "")),
                product_type=str(it.get("productType", "")),
                link=it.get("link", ""),
                image=it.get("image", ""),
                category=cat,
                brand=it.get("brand", ""),
                maker=it.get("maker", ""),
            )
        )
    return NaverSearchResult(query=query, total=int(data.get("total") or 0), items=items)
