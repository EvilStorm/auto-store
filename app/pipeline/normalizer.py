"""② 사전 정규화기 (DESIGN.md 6-②). LLM 0회.

실행 순서: 규칙 세트(active, 카테고리 → 소스 기본 상속) → 공용 사전 → 확인 큐(missing).
규칙 세트가 아직 없으면 내장 기본 규칙(DEFAULT_RULES)으로 돈다 — 1688 제목·속성표의 일반 패턴.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.taxonomy import engine
from app.taxonomy.dictionary import Category, Dictionary

# 소스·카테고리 규칙 세트가 없을 때의 기본. 규칙 생성기(generate.py)가 이걸 출발점으로 삼는다.
DEFAULT_RULES: list[dict] = [
    {"op": "strip", "from": "title_raw", "as": "title_clean"},
    {"op": "unit", "from": "title_raw", "as": "numbers"},
    {"op": "select", "from": "attrs_raw", "path": "材质", "as": "material_raw"},
    {"op": "select", "from": "attrs_raw", "path": "品牌", "as": "brand_attr"},
    {"op": "map", "kind": "material", "from": "material_raw", "as": "material_code"},
    {"op": "default", "field": "item_type", "from_category": True},
    {"op": "default", "field": "canonical_category_id", "from_category": True, "attr": "id"},
    {"op": "flag", "from": "title_raw", "pattern": "充电|电池|USB|无线|蓝牙|插电|LED|电动", "name": "maybe_electronics"},
    {"op": "flag", "from": "title_raw", "pattern": "儿童|婴儿|宝宝|幼儿|キッズ|ベビー", "name": "maybe_kids"},
    {"op": "flag", "from": "title_raw", "pattern": "食品|零食|饮料|咖啡豆|茶叶|保健", "name": "maybe_food"},
    {"op": "template", "text": "{kw0} {capacity}", "as": "q1"},
    {"op": "template", "text": "{kw1} {material_ko}", "as": "q2"},
    {"op": "template", "text": "{kw0}", "as": "q3"},
]

MATERIAL_KO = {"stainless": "스테인리스", "glass": "유리", "ceramic": "도자기", "silicone": "실리콘", "plastic": "플라스틱",
               "wood": "원목", "metal": "메탈", "fabric": "패브릭", "paper": "종이", "battery": "배터리", "magnet": "자석", "liquid": "액체"}

FIELDS_FOR_COVERAGE = ["title_clean", "numbers", "material_code", "item_type", "canonical_category_id", "search_queries"]


@dataclass
class NormalizedItem:
    title_clean: str
    key_numbers: dict[str, list[float]]
    material_code: str | None
    item_type: str
    canonical_category_id: str | None
    search_queries: list[str]
    brand_text_hit: str | None
    excluded_reason: str | None
    requirement_status: str
    requirement_reason: str
    flags: list[str]
    missing: list[dict] = field(default_factory=list)   # 사전에 없는 표기 → mapping_queue
    dict_version: int = 0
    ruleset_version: int | None = None


def build_ctx(raw: dict[str, Any], category: Category | None, d: Dictionary, extra_keywords: list[str] | None = None) -> dict:
    """RawListing dict → 엔진 입력. kw0·kw1 은 카테고리(또는 관심 카테고리의 추가 키워드)의 한국어 검색 키워드."""
    kws = list(extra_keywords or []) + (category.search_keywords_ko if category else [])
    ctx = {
        "title_raw": raw.get("title_raw") or "",
        "attrs_raw": raw.get("attrs_raw") or {},
        "category_raw": raw.get("category_raw") or "",
        "price_raw": raw.get("price_raw"),
        "category": category,
        "kw0": kws[0] if len(kws) > 0 else None,
        "kw1": kws[1] if len(kws) > 1 else (kws[0] if kws else None),
        "kw2": kws[2] if len(kws) > 2 else None,
    }
    return ctx


def normalize(raw: dict[str, Any], category: Category | None, d: Dictionary, *, rules: list[dict] | None = None,
              ruleset_version: int | None = None, extra_keywords: list[str] | None = None) -> NormalizedItem:
    ctx = build_ctx(raw, category, d, extra_keywords)
    res = engine.run(rules or DEFAULT_RULES, ctx, d)
    c = res.ctx

    # 재질 한국어 (템플릿 재료) — map 결과가 있을 때만. 템플릿은 이미 돌았으니 q2 를 다시 만든다
    if c.get("material_code"):
        c["material_ko"] = MATERIAL_KO.get(c["material_code"], "")
        if c.get("kw1") and c["material_ko"]:
            c["q2"] = f"{c['kw1']} {c['material_ko']}"

    # 카테고리 표기(빵부스러기)가 사전과 다르면 사전을 우선하되 상속값과 다르면 큐에
    cat_id = c.get("canonical_category_id")
    if c.get("category_raw"):
        hit = d.category_for_term(str(c["category_raw"]))
        if hit and cat_id and hit != cat_id:
            c["missing"].append({"kind": "category", "term": str(c["category_raw"]), "note": f"상속 {cat_id} ≠ 사전 {hit}"})
        elif not hit and not cat_id:
            c["missing"].append({"kind": "category", "term": str(c["category_raw"])})
        cat_id = cat_id or hit

    # 품목 유형: 플래그로 보수적 승격 (전자 · 아동 · 식품 의심은 더 엄한 쪽으로)
    item_type = c.get("item_type") or "general"
    flags = set(c.get("flags") or set())
    if "maybe_food" in flags:
        item_type = "food"
    elif "maybe_kids" in flags and item_type == "general":
        item_type = "kids"
    elif "maybe_electronics" in flags and item_type == "general":
        item_type = "electronics"

    # 브랜드 텍스트: 제목 + 品牌 속성
    brand_hits = d.brand_hits(" ".join(str(x) for x in (c.get("title_raw"), c.get("brand_attr")) if x))
    brand_hit = brand_hits[0] if brand_hits else None

    status, reason = d.requirement(item_type)
    excluded = None
    if status == "excluded":
        excluded = item_type
    elif brand_hit:
        excluded = "brand_text"

    queries = [c[k] for k in ("q1", "q2", "q3") if c.get(k)]
    dedup: list[str] = []
    for q in queries:
        if q not in dedup:
            dedup.append(q)

    return NormalizedItem(
        title_clean=c.get("title_clean") or c.get("title_raw") or "",
        key_numbers=c.get("numbers") or {},
        material_code=c.get("material_code"),
        item_type=item_type,
        canonical_category_id=cat_id,
        search_queries=dedup[:3],
        brand_text_hit=brand_hit,
        excluded_reason=excluded,
        requirement_status=status,
        requirement_reason=reason,
        flags=sorted(flags),
        missing=list(c.get("missing") or []),
        dict_version=d.dict_version,
        ruleset_version=ruleset_version,
    )


def to_row(source_item_id: int, n: NormalizedItem) -> dict:
    """source_items_normalized 행."""
    return {
        "source_item_id": source_item_id,
        "dict_version": n.dict_version,
        "ruleset_version": n.ruleset_version,
        "title_clean": n.title_clean,
        "key_numbers_json": n.key_numbers,
        "material_code": n.material_code,
        "item_type": n.item_type,
        "canonical_category_id": n.canonical_category_id,
        "search_queries": n.search_queries,
        "brand_text_hit": n.brand_text_hit,
        "excluded_reason": n.excluded_reason,
        "mapping_pending": bool(n.missing),
    }
