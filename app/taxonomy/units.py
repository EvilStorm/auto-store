"""제목·속성에서 숫자+단위를 뽑아 표준 단위로 바꾼다. LLM 없이 결정적으로.

extract_numbers("不锈钢保温杯 500ml 大容量 1.2L 带手柄 40oz") →
  {"capacity_ml": [500, 1200, 1183], "length_mm": [], ...}
키는 규칙 세트 match_hints 와 검색어 템플릿이 그대로 쓴다.
"""
from __future__ import annotations

import re

# (정규식, 표준 키, 변환 계수 또는 함수). 숫자는 소수 허용, 단위는 대소문자 무시, 전각 공백 허용.
_NUM = r"(\d+(?:[.,]\d+)?)"
PATTERNS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(_NUM + r"\s*(?:ml|mL|ML|毫升|㎖)", re.I), "capacity_ml", 1.0),
    (re.compile(_NUM + r"\s*(?:l|L|升|리터|ℓ)(?![a-zA-Z])"), "capacity_ml", 1000.0),
    (re.compile(_NUM + r"\s*(?:oz|OZ|온스|盎司)", re.I), "capacity_ml", 29.5735),
    (re.compile(_NUM + r"\s*(?:mm|毫米|㎜)", re.I), "length_mm", 1.0),
    (re.compile(_NUM + r"\s*(?:cm|厘米|公分|㎝|센치|센티)", re.I), "length_mm", 10.0),
    (re.compile(_NUM + r"\s*(?:inch|in\b|英寸|인치|\")", re.I), "length_mm", 25.4),
    (re.compile(_NUM + r"\s*(?:kg|KG|公斤|킬로)", re.I), "weight_g", 1000.0),
    (re.compile(_NUM + r"\s*(?:g|G|克|그램)(?![a-zA-Z])"), "weight_g", 1.0),
    (re.compile(_NUM + r"\s*(?:mAh|mah|毫安)", re.I), "battery_mah", 1.0),
    (re.compile(_NUM + r"\s*(?:w|W|瓦)(?![a-zA-Z])"), "power_w", 1.0),
    (re.compile(_NUM + r"\s*(?:개입|个装|个|枚|pcs|PCS|件套|套)", re.I), "pack_count", 1.0),
]

# "30*20*10cm" 같은 치수 표기
DIMS = re.compile(r"(\d+(?:\.\d+)?)\s*[x×\*]\s*(\d+(?:\.\d+)?)(?:\s*[x×\*]\s*(\d+(?:\.\d+)?))?\s*(cm|mm|厘米|毫米)?", re.I)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def extract_numbers(text: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    if not text:
        return out
    for pat, key, k in PATTERNS:
        for m in pat.finditer(text):
            v = round(_num(m.group(1)) * k, 1)
            if v <= 0:
                continue
            out.setdefault(key, [])
            if v not in out[key]:
                out[key].append(v)
    for m in DIMS.finditer(text):
        unit = (m.group(4) or "").lower()
        k = 10.0 if unit in ("cm", "厘米") else 1.0 if unit in ("mm", "毫米") else None
        if k is None:
            continue
        dims = [round(_num(g) * k, 1) for g in m.groups()[:3] if g]
        out.setdefault("dims_mm", [])
        if dims not in out["dims_mm"]:
            out["dims_mm"].append(dims)  # type: ignore[arg-type]
    return out


def primary(numbers: dict[str, list[float]], key: str) -> float | None:
    """대표값: 첫 번째로 나온 값 (제목 앞쪽이 보통 핵심 스펙)."""
    v = numbers.get(key)
    return v[0] if v else None


def format_capacity(ml: float | None) -> str:
    if ml is None:
        return ""
    if ml >= 1000 and abs(ml / 1000 - round(ml / 1000, 1)) < 1e-6:
        return f"{ml / 1000:g}L"
    return f"{int(round(ml))}ml"


def numbers_agree(a: dict, b: dict, key: str, tol: float = 0.08) -> bool | None:
    """두 상품의 핵심 숫자가 일치하는가. 둘 중 하나라도 없으면 None(판단 불가)."""
    x, y = primary(a, key), primary(b, key)
    if x is None or y is None:
        return None
    return abs(x - y) <= tol * max(x, y)
