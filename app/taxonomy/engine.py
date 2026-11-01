"""규칙 세트 DSL 엔진 (DESIGN.md 3.5).

규칙 세트 = {"kind": "normalize", "rules": [ {op, ...}, ... ]}. 연산 8개만 있고 임의 코드는 없다.
입력(ctx)은 평평한 dict 로 시작해 규칙이 필드를 추가한다. 모든 연산은 결정적이다.

  select    {"op":"select","from":"attrs_raw","path":"材质","as":"material_raw"}          dict 경로/키 또는 JSON 포인터 꺼내기
  regex     {"op":"regex","from":"title_raw","pattern":"(\\d+)\\s*ml","group":1,"as":"cap","first":true}
  unit      {"op":"unit","from":"title_raw","as":"numbers"}                               숫자+단위 → units.extract_numbers
  strip     {"op":"strip","from":"title_raw","as":"title_clean","extra":["热卖"]}          스톱워드(사전 + extra) 제거
  map       {"op":"map","kind":"material","from":"material_raw","as":"material_code"}       사전 코드화 (없으면 null → 큐)
  template  {"op":"template","text":"{kw0} {capacity}","as":"q1","skip_if_missing":true}    문자열 조합
  default   {"op":"default","field":"item_type","from_category":true}                       카테고리 상속 / 고정값 {"value":...}
  flag      {"op":"flag","from":"title_raw","pattern":"充电|电池|USB","name":"maybe_electronics"}
  terms     {"op":"terms","kind":"feature","from":"title_raw","as":"features","max":3}        사전 표기 전부 → 코드 목록 + features0/1/2 에 한국어

map 은 코드와 함께 <as 에서 _code 를 뗀 이름>_ko (예: material_ko) 에 한국어 표기를 넣는다. queue_if_missing:false 면 미등록 표기를 큐에 안 넣는다
(제목처럼 재질이 아예 없을 수도 있는 입력에 쓴다). keep_existing:true 면 이미 값이 있을 때 덮어쓰지 않는다.
ctx 예약 필드: category (Category), dict (Dictionary), numbers (unit 결과), flags (set), missing (list: map 실패 표기)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.taxonomy import units
from app.taxonomy.dictionary import Category, Dictionary


class RuleError(ValueError):
    pass


@dataclass
class RunResult:
    ctx: dict[str, Any]
    applied: list[str] = field(default_factory=list)   # 적용된 규칙 설명
    errors: list[str] = field(default_factory=list)


def _get(ctx: dict, path: str) -> Any:
    """'attrs_raw.材质' 또는 'attrs_raw/材质' 식 경로. 없으면 None."""
    cur: Any = ctx
    for part in re.split(r"[./]", path):
        if part == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)] if int(part) < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _fmt(template: str, ctx: dict) -> tuple[str, bool]:
    """{field} 치환. 하나라도 비면 (text, False)."""
    ok = True

    def rep(m):
        nonlocal ok
        v = _get(ctx, m.group(1))
        if v is None or v == "" or v == []:
            ok = False
            return ""
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)

    return re.sub(r"\{([^{}]+)\}", rep, template), ok


def run(rules: list[dict], ctx: dict[str, Any], d: Dictionary) -> RunResult:
    ctx = dict(ctx)
    ctx.setdefault("flags", set())
    ctx.setdefault("missing", [])
    ctx["dict"] = d
    res = RunResult(ctx=ctx)
    for i, r in enumerate(rules):
        op = r.get("op")
        try:
            if op == "select":
                src = _get(ctx, r["from"]) if "from" in r else ctx
                val = _get(src, r["path"]) if isinstance(src, dict) and "path" in r else src
                ctx[r["as"]] = val
            elif op == "regex":
                text = str(_get(ctx, r["from"]) or "")
                pat = re.compile(r["pattern"], re.I if r.get("ignore_case", True) else 0)
                grp = r.get("group", 0)
                found = [m.group(grp) for m in pat.finditer(text)]
                ctx[r["as"]] = (found[0] if found else None) if r.get("first", True) else found
            elif op == "unit":
                text = str(_get(ctx, r["from"]) or "")
                nums = units.extract_numbers(text)
                key = r.get("as", "numbers")
                merged = dict(ctx.get(key) or {})
                for k, v in nums.items():
                    merged.setdefault(k, [])
                    merged[k] += [x for x in v if x not in merged[k]]
                ctx[key] = merged
                cap = units.primary(merged, "capacity_ml")
                if cap is not None:
                    ctx.setdefault("capacity", units.format_capacity(cap))
            elif op == "strip":
                text = str(_get(ctx, r["from"]) or "")
                for w in r.get("extra", []):
                    text = text.replace(w, " ")
                ctx[r["as"]] = d.strip_stopwords(text)
            elif op == "map":
                raw = _get(ctx, r["from"])
                code = d.code_for(r["kind"], str(raw)) if raw else None
                if raw and code is None and r.get("queue_if_missing", True):
                    ctx["missing"].append({"kind": r["kind"], "term": str(raw)[:120]})
                if code is not None or not r.get("keep_existing", False) or ctx.get(r["as"]) is None:
                    if not (r.get("keep_existing") and ctx.get(r["as"])):
                        ctx[r["as"]] = code
                if ctx.get(r["as"]):
                    ctx[r["as"].replace("_code", "") + "_ko"] = d.ko_for(r["kind"], ctx[r["as"]])
            elif op == "terms":
                # 텍스트에서 kind 사전 표기를 전부 찾아 코드 목록으로. as, as0, as1 … 에 넣어 템플릿이 쓰게 한다
                text = str(_get(ctx, r["from"]) or "")
                codes = d.terms_for(r["kind"], text, int(r.get("max", 5)))
                ctx[r["as"]] = codes
                for i, code in enumerate(codes):
                    ctx[f"{r['as']}{i}"] = d.ko_for(r["kind"], code) or code
            elif op == "template":
                text, ok = _fmt(r["text"], ctx)
                if ok or not r.get("skip_if_missing", True):
                    ctx[r["as"]] = " ".join(text.split())
            elif op == "default":
                f = r["field"]
                if ctx.get(f) in (None, "", []):
                    if r.get("from_category"):
                        cat: Category | None = ctx.get("category")
                        if cat is not None:
                            ctx[f] = getattr(cat, r.get("attr", f), None)
                    elif "value" in r:
                        ctx[f] = r["value"]
            elif op == "flag":
                text = str(_get(ctx, r["from"]) or "")
                if re.search(r["pattern"], text, re.I):
                    ctx["flags"].add(r["name"])
            else:
                raise RuleError(f"알 수 없는 op: {op!r}")
            res.applied.append(f"{i}:{op}")
        except RuleError:
            raise
        except Exception as e:  # 규칙 하나의 오류가 전체를 멈추지 않게 — 커버리지에서 드러난다
            res.errors.append(f"{i}:{op}: {type(e).__name__}: {e}")
    return res


def validate(rules: list[dict]) -> list[str]:
    """구조 검증 (LLM 이 만든 초안을 받을 때). 오류 메시지 목록, 비어 있으면 통과."""
    allowed = {"select", "regex", "unit", "strip", "map", "template", "default", "flag", "terms"}
    need = {"select": ["as"], "regex": ["from", "pattern", "as"], "unit": ["from"], "strip": ["from", "as"],
            "map": ["kind", "from", "as"], "template": ["text", "as"], "default": ["field"], "flag": ["from", "pattern", "name"],
            "terms": ["kind", "from", "as"]}
    errs = []
    if not isinstance(rules, list):
        return ["rules 는 배열이어야 합니다"]
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or r.get("op") not in allowed:
            errs.append(f"{i}: op 가 {sorted(allowed)} 중 하나여야 합니다")
            continue
        for k in need[r["op"]]:
            if k not in r:
                errs.append(f"{i}:{r['op']}: '{k}' 누락")
        if r["op"] in ("regex", "flag"):
            try:
                re.compile(r.get("pattern", ""))
            except re.error as e:
                errs.append(f"{i}:{r['op']}: 정규식 오류 {e}")
    return errs


def coverage(rules: list[dict], samples: list[dict], d: Dictionary, fields: list[str]) -> dict[str, float]:
    """샘플마다 규칙을 돌려 각 필드가 채워진 비율(%). '_overall' 은 평균, '_errors' 는 오류 난 규칙 수."""
    if not samples:
        return {f: 0.0 for f in fields} | {"_overall": 0.0, "_errors": 0}
    filled = {f: 0 for f in fields}
    errors = 0
    for s in samples:
        r = run(rules, s, d)
        errors += len(r.errors)
        for f in fields:
            v = r.ctx.get(f)
            if v not in (None, "", [], {}):
                filled[f] += 1
    pct = {f: round(100.0 * filled[f] / len(samples), 1) for f in fields}
    pct["_overall"] = round(sum(pct.values()) / len(fields), 1) if fields else 0.0
    pct["_errors"] = errors
    return pct
