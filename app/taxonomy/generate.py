"""규칙 세트 생성기 (DESIGN.md 3.5): 샘플 → LLM 1회 → DSL 초안 → 검증(커버리지) → draft 저장.

  python -m app.taxonomy.generate --source 1688 --category kitchen.tumbler --samples samples.json [--dry-run]

LLM 은 코드가 아니라 규칙(JSON)만 낸다. 받은 초안은 engine.validate 로 구조를 검사하고, 샘플 전체에 돌려
필드별 커버리지를 낸다. 홀드아웃(마지막 20%)은 커버리지 계산에만 쓰고 LLM 에는 주지 않는다.
이 LLM 호출도 ai_results 캐시를 거친다 — 같은 샘플이면 두 번째 요청은 호출 0.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.adapters.llm.base import LLM
from app.pipeline.normalizer import DEFAULT_RULES, FIELDS_FOR_COVERAGE, build_ctx
from app.taxonomy import engine
from app.taxonomy.dictionary import Category, Dictionary

SYSTEM = (
    "너는 해외 도매 상품 데이터 정규화 규칙을 설계하는 엔지니어다. 상품마다 LLM 을 부르지 않기 위해, 샘플에서 반복되는 "
    "패턴을 읽어 결정적 규칙(JSON DSL)으로 굳힌다. 코드를 쓰지 말고 아래 8가지 연산만 조합한다.\n"
    "연산: select(from,path,as) · regex(from,pattern,group,as,first) · unit(from,as) · strip(from,as,extra[]) · "
    "map(kind,from,as) · template(text,as) · default(field,from_category|value) · flag(from,pattern,name)\n"
    "목표 필드: title_clean(광고어 제거 제목), numbers(unit 결과), material_code(map material), item_type, "
    "canonical_category_id, q1/q2/q3(한국어 네이버 검색어 2~3개: 카테고리 키워드 {kw0}/{kw1} + {capacity} 또는 {material_ko}).\n"
    "규칙은 샘플에 과적합하지 말고 그 카테고리의 일반 패턴을 잡는다. 각 규칙에 근거를 한 줄 적는다."
)


class RuleOut(BaseModel):
    op: Literal["select", "regex", "unit", "strip", "map", "template", "default", "flag"]
    params: dict = Field(description="연산 인자 (op 제외). 예: {\"from\":\"title_raw\",\"as\":\"title_clean\"}")
    rationale: str = Field(description="이 규칙이 필요한 근거 한 줄")


class RulesetDraft(BaseModel):
    rules: list[RuleOut]
    extra_stopwords: list[str] = Field(default_factory=list, description="이 소스·카테고리 제목에 반복되는 광고어 (사전에 없는 것)")
    notes: str = Field(description="샘플에서 본 패턴 요약과 규칙으로 못 잡은 것")


def _samples_prompt(samples: list[dict], category: Category | None, d: Dictionary) -> str:
    lines = [f"표준 카테고리: {category.path if category else '(없음)'} · 한국어 키워드: {category.search_keywords_ko if category else []}",
             f"사전 재질 코드: {sorted(set(d.attribute_aliases.values()))}",
             f"사전 스톱워드 예: {sorted(d.stopwords)[:15]}", "", f"샘플 {len(samples)}건 (제목 · 속성표 · 분류 표기):"]
    for i, s in enumerate(samples):
        attrs = s.get("attrs_raw") or {}
        lines.append(f"[{i}] {s.get('title_raw', '')}")
        if attrs:
            lines.append(f"     속성: {json.dumps(attrs, ensure_ascii=False)[:300]}")
        if s.get("category_raw"):
            lines.append(f"     분류: {s['category_raw']}")
    lines.append("")
    lines.append("기본 규칙(출발점, 그대로 쓰거나 고치거나 추가):")
    lines.append(json.dumps(DEFAULT_RULES, ensure_ascii=False))
    return "\n".join(lines)


def draft_to_rules(draft: RulesetDraft) -> tuple[list[dict], list[dict]]:
    rules, rationale = [], []
    for r in draft.rules:
        rule = {"op": r.op, **r.params}
        if r.op == "strip" and draft.extra_stopwords:
            rule["extra"] = sorted(set(rule.get("extra", [])) | set(draft.extra_stopwords))
        rules.append(rule)
        rationale.append({"op": r.op, "why": r.rationale})
    return rules, rationale


def generate(llm: LLM, samples: list[dict], category: Category | None, d: Dictionary, *, holdout_ratio: float = 0.2) -> dict:
    """반환: {rules, rationale, coverage, holdout_coverage, errors, notes, cost_krw, cache_hit}."""
    n_hold = max(1, int(len(samples) * holdout_ratio)) if len(samples) >= 5 else 0
    train, hold = samples[: len(samples) - n_hold], samples[len(samples) - n_hold:]
    prompt = _samples_prompt(train, category, d)
    before = len(llm.usage)
    draft = llm.complete_json(prompt, RulesetDraft, system=SYSTEM, purpose="ruleset_generate", effort="medium")
    rec = llm.usage[-1] if len(llm.usage) > before else None
    rules, rationale = draft_to_rules(draft)
    errors = engine.validate(rules)
    if errors:
        # 구조가 깨진 규칙은 버리고 기본 규칙으로 — 커버리지가 말해준다
        rules = [r for i, r in enumerate(rules) if not any(e.startswith(f"{i}:") for e in errors)] or list(DEFAULT_RULES)
    ctxs = [build_ctx(s, category, d) for s in samples]
    cov = engine.coverage(rules, [build_ctx(s, category, d) for s in train], d, FIELDS_FOR_COVERAGE[:-1] + ["q1"])
    hold_cov = engine.coverage(rules, [build_ctx(s, category, d) for s in hold], d, FIELDS_FOR_COVERAGE[:-1] + ["q1"]) if hold else {}
    return {
        "rules": rules,
        "rationale": rationale,
        "coverage": cov,
        "holdout_coverage": hold_cov,
        "errors": errors,
        "notes": draft.notes,
        "extra_stopwords": draft.extra_stopwords,
        "cost_krw": rec.est_cost_krw if rec else 0.0,
        "cache_hit": bool(rec and rec.cache_hit),
        "n_samples": len(samples),
        "_ctx_count": len(ctxs),
    }


def main(argv=None) -> int:
    import argparse
    import sys

    from app.adapters.llm import get_llm
    from app.taxonomy import dictionary

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", help="표준 카테고리 id (없으면 소스 기본 세트)")
    ap.add_argument("--samples", required=True, help="RawListing dict 배열 JSON (s1688 --test 출력)")
    ap.add_argument("--dry-run", action="store_true", help="DB 에 draft 저장 안 함")
    a = ap.parse_args(argv)

    samples = json.loads(open(a.samples, encoding="utf-8").read())
    try:
        from app.db import user_client

        client = user_client()
        d = dictionary.from_db(client)
    except Exception as e:
        print(f"(DB 미연결: {type(e).__name__} → 시드 사전으로 진행, 저장 안 함)")
        client, d = None, dictionary.from_seed()
        a.dry_run = True
    cat = d.categories.get(a.category) if a.category else None
    if client:
        from app.ai_cache import SupabaseCache, set_backend

        set_backend(SupabaseCache(client))
    out = generate(get_llm(), samples, cat, d)
    print(json.dumps({k: v for k, v in out.items() if k != "rules"}, ensure_ascii=False, indent=1))
    print("rules:", json.dumps(out["rules"], ensure_ascii=False))
    if client and not a.dry_run:
        row = {"source_id": a.source, "canonical_category_id": a.category, "kind": "normalize", "rules_json": out["rules"],
               "rationale_json": out["rationale"], "coverage_json": {**out["coverage"], "_holdout": out["holdout_coverage"]},
               "status": "draft", "generated_by": "llm"}
        res = client.table("rulesets").insert(row).execute()
        print("draft 저장:", res.data[0]["id"] if res.data else "?", "→ 관리자 승인 후 active")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
