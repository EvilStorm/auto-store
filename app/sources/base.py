"""소스 어댑터 계약 (DESIGN.md 3.2). 어댑터는 원시 데이터만 돌려주고 해석은 ② 정규화기가 한다."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterator


@dataclass
class RawListing:
    source_id: str
    item_id: str
    url: str
    title_raw: str
    lang: str = "zh"
    price_raw: str = ""                       # "¥12.5" · "¥12.5-15.0" 원문
    price_tiers: list[dict] = field(default_factory=list)   # [{min_qty, unit_price}] 파싱 가능하면
    currency: str = "CNY"
    moq: int = 1
    image_url: str = ""
    category_raw: str = ""
    attrs_raw: dict[str, Any] = field(default_factory=dict)
    weight_raw: str = ""
    sold_out: bool = False
    extra: dict[str, Any] = field(default_factory=dict)      # 판매량 · 회사명 등 소스별 덤

    def to_dict(self) -> dict:
        return asdict(self)

    def to_row(self) -> dict:
        """source_items upsert 행."""
        return {
            "source_id": self.source_id,
            "source_item_id": self.item_id,
            "url": self.url,
            "title_raw": self.title_raw,
            "lang": self.lang,
            "price_tiers_json": self.price_tiers,
            "currency": self.currency,
            "moq": self.moq,
            "main_image_url": self.image_url or None,
            "category_raw": self.category_raw or None,
            "attrs_raw_json": self.attrs_raw,
            "weight_raw": self.weight_raw or None,
            "sold_out": self.sold_out,
            "last_price_src": (self.price_tiers[0]["unit_price"] if self.price_tiers else None),
        }


@dataclass
class RawDetail(RawListing):
    options: list[dict] = field(default_factory=list)    # [{sku_id, name_raw, price, image, sold_out}]
    images: list[str] = field(default_factory=list)
    attrs_full: dict[str, Any] = field(default_factory=dict)
    package_weight_raw: str = ""


class Blocked(RuntimeError):
    """캡차 · 로그인 요구 · 차단. 소스 단위로 당일 중단 판단에 쓴다."""


class SourceAdapter:
    key: str = "base"

    def __init__(self, *, profile_dir=None, headed: bool = False, delay_range=(2.0, 6.0)):
        self.profile_dir = profile_dir
        self.headed = headed
        self.delay_range = delay_range

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self) -> None: ...
    def close(self) -> None: ...

    def list(self, list_url: str, page: int = 1) -> list[RawListing]:
        raise NotImplementedError

    def iter_pages(self, list_url: str, max_pages: int) -> Iterator[tuple[int, list[RawListing]]]:
        for p in range(1, max_pages + 1):
            items = self.list(list_url, p)
            yield p, items
            if not items:
                break

    def detail(self, item_url: str) -> RawDetail:
        raise NotImplementedError
