"""공용 사전(별칭 · 속성 코드 · 브랜드 · 스톱워드 · 표준 카테고리 · 요건표).

DB(Supabase) 에서 읽는 것이 기본이고, 테스트·오프라인에서는 supabase/seed/*.csv 를 그대로 읽는다.
어느 쪽이든 같은 Dictionary 객체가 나오므로 엔진·정규화기는 출처를 모른다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEED = ROOT / "supabase" / "seed"


@dataclass
class Category:
    id: str
    parent_id: str | None
    path: str
    naver_cat_id: str | None
    item_type: str
    default_weight_g: int
    search_keywords_ko: list[str]


@dataclass
class Dictionary:
    dict_version: int = 0
    categories: dict[str, Category] = field(default_factory=dict)
    category_aliases: dict[tuple[str, str], str] = field(default_factory=dict)  # (term_lower, lang) → category id
    attribute_aliases: dict[tuple[str, str], str] = field(default_factory=dict)  # (kind, term_lower) → code
    code_ko: dict[tuple[str, str], str] = field(default_factory=dict)  # (kind, code) → 한국어 표기
    brand_blacklist: dict[str, str] = field(default_factory=dict)  # name_lower → kind
    stopwords: set[str] = field(default_factory=set)
    requirements: dict[str, tuple[str, str]] = field(default_factory=dict)  # item_type → (status, reason)

    # ── 조회 ──
    def category_for_term(self, term: str, lang: str | None = None) -> str | None:
        t = term.strip().lower()
        if lang:
            return self.category_aliases.get((t, lang))
        for lg in ("zh", "ja", "ko", "en"):
            c = self.category_aliases.get((t, lg))
            if c:
                return c
        return None

    def category_for_text(self, text: str) -> str | None:
        """빵부스러기가 없을 때: 제목 안에서 가장 긴 카테고리 별칭 표기를 찾아 그 표준 카테고리로 (保温杯 → kitchen.tumbler)."""
        t = (text or "").lower()
        best = None
        for (term, _lang), cid in self.category_aliases.items():
            if len(term) >= 2 and term in t and (best is None or len(term) > len(best[0])):
                best = (term, cid)
        return best[1] if best else None

    def code_for(self, kind: str, term: str) -> str | None:
        t = term.strip().lower()
        if (kind, t) in self.attribute_aliases:
            return self.attribute_aliases[(kind, t)]
        # 속성값 안에 사전 표기가 포함된 경우 (예: "304不锈钢材质" ⊃ "304不锈钢")
        best = None
        for (k, alias), code in self.attribute_aliases.items():
            if k == kind and alias in t and (best is None or len(alias) > len(best[0])):
                best = (alias, code)
        return best[1] if best else None

    def terms_for(self, kind: str, text: str, max_terms: int = 5) -> list[str]:
        """텍스트 안에서 kind 사전의 표기를 전부 찾아 코드 목록으로 (등장 순서 · 겹치지 않게 · 긴 표기 우선). 특징어 추출용."""
        t = (text or "").lower()
        hits: list[tuple[int, int, str]] = []
        for (k, alias), code in sorted(self.attribute_aliases.items(), key=lambda kv: -len(kv[0][1])):
            if k != kind or len(alias) < 2:
                continue
            start = 0
            while True:
                i = t.find(alias, start)
                if i < 0:
                    break
                if not any(i < e and i + len(alias) > s for s, e, _ in hits):
                    hits.append((i, i + len(alias), code))
                start = i + len(alias)
        out: list[str] = []
        for _, _, code in sorted(hits):
            if code not in out:
                out.append(code)
        return out[:max_terms]

    def ko_for(self, kind: str, code: str | None) -> str:
        """코드 → 한국어 표기 (ko 별칭 중 첫 것). 없으면 ''."""
        if not code:
            return ""
        return self.code_ko.get((kind, code), "")

    def brand_hits(self, text: str) -> list[str]:
        low = (text or "").lower()
        hits = []
        for name in self.brand_blacklist:
            if len(name) >= 2 and name in low:
                hits.append(name)
        return hits

    def strip_stopwords(self, text: str) -> str:
        t = text or ""
        for w in sorted(self.stopwords, key=len, reverse=True):
            t = t.replace(w, " ")
        return " ".join(t.split())

    def requirement(self, item_type: str) -> tuple[str, str]:
        return self.requirements.get(item_type, ("pass", "요건표에 없는 품목 유형 — 확인 필요"))

    def ancestors(self, cat_id: str) -> list[Category]:
        out = []
        cur = self.categories.get(cat_id)
        while cur:
            out.append(cur)
            cur = self.categories.get(cur.parent_id) if cur.parent_id else None
        return out


# ── 로더: CSV (오프라인 · 테스트) ──
def _read_csv(name: str) -> list[dict]:
    p = SEED / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in csv.DictReader(f)]


def from_seed() -> Dictionary:
    d = Dictionary(dict_version=1)
    for r in _read_csv("canonical_categories.csv"):
        d.categories[r["id"]] = Category(
            id=r["id"], parent_id=r["parent_id"] or None, path=r["path"], naver_cat_id=r["naver_cat_id"] or None,
            item_type=r["item_type"] or "general", default_weight_g=int(r["default_weight_g"] or 0),
            search_keywords_ko=[x.strip() for x in r["search_keywords_ko"].split("|") if x.strip()],
        )
    for r in _read_csv("category_aliases.csv"):
        d.category_aliases[(r["term"].lower(), r["lang"])] = r["canonical_category_id"]
    for r in _read_csv("attribute_aliases.csv"):
        d.attribute_aliases[(r["kind"], r["term"].lower())] = r["code"]
        if r["lang"] == "ko":
            d.code_ko.setdefault((r["kind"], r["code"]), r["term"])
    for r in _read_csv("brand_blacklist.csv"):
        d.brand_blacklist[r["name"].lower()] = r["kind"]
    for r in _read_csv("title_stopwords.csv"):
        d.stopwords.add(r["term"])
    for r in _read_csv("requirements.csv"):
        d.requirements[r["item_type"]] = (r["status"], r["reason"])
    return d


# ── 로더: Supabase ──
def from_db(client) -> Dictionary:
    d = Dictionary()
    d.dict_version = int(client.rpc("current_dict_version").execute().data or 0)
    for r in client.table("canonical_categories").select("*").execute().data:
        d.categories[r["id"]] = Category(
            id=r["id"], parent_id=r.get("parent_id"), path=r["path"], naver_cat_id=r.get("naver_cat_id"),
            item_type=r.get("item_type") or "general", default_weight_g=int(r.get("default_weight_g") or 0),
            search_keywords_ko=list(r.get("search_keywords_ko") or []),
        )
    for r in client.table("category_aliases").select("term, lang, canonical_category_id").execute().data:
        d.category_aliases[(r["term"].lower(), r["lang"])] = r["canonical_category_id"]
    for r in client.table("attribute_aliases").select("kind, term, lang, code").execute().data:
        d.attribute_aliases[(r["kind"], r["term"].lower())] = r["code"]
        if r.get("lang") == "ko":
            d.code_ko.setdefault((r["kind"], r["code"]), r["term"])
    for r in client.table("brand_blacklist").select("name, kind").execute().data:
        d.brand_blacklist[r["name"].lower()] = r["kind"]
    for r in client.table("title_stopwords").select("term").execute().data:
        d.stopwords.add(r["term"])
    for r in client.table("requirements").select("item_type, status, reason").execute().data:
        d.requirements[r["item_type"]] = (r["status"], r["reason"])
    return d
