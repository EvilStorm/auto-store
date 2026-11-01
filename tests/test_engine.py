from app.taxonomy import engine

RULES = [
    {"op": "strip", "from": "title_raw", "as": "title_clean", "extra": ["热卖"]},
    {"op": "unit", "from": "title_raw", "as": "numbers"},
    {"op": "select", "from": "attrs_raw", "path": "材质", "as": "material_raw"},
    {"op": "map", "kind": "material", "from": "material_raw", "as": "material_code"},
    {"op": "regex", "from": "title_raw", "pattern": r"(\d+)\s*件套", "group": 1, "as": "set_count"},
    {"op": "default", "field": "item_type", "from_category": True},
    {"op": "flag", "from": "title_raw", "pattern": "USB|充电", "name": "maybe_electronics"},
    {"op": "template", "text": "{kw0} {capacity}", "as": "q1"},
    {"op": "template", "text": "{kw1} {missing_field}", "as": "q2"},
]


def ctx(d, **over):
    base = {"title_raw": "跨境爆款 热卖 304不锈钢保温杯 500ml 便携 USB", "attrs_raw": {"材质": "304不锈钢材质"},
            "category": d.categories["kitchen.tumbler"], "kw0": "텀블러", "kw1": "보온병"}
    base.update(over)
    return base


def test_run_all_ops(d):
    r = engine.run(RULES, ctx(d), d)
    c = r.ctx
    assert not r.errors
    assert "跨境" not in c["title_clean"] and "热卖" not in c["title_clean"] and "保温杯" in c["title_clean"]
    assert c["numbers"]["capacity_ml"] == [500.0]
    assert c["capacity"] == "500ml"
    assert c["material_code"] == "stainless"          # 부분 일치 (304不锈钢 ⊂ 304不锈钢材质)
    assert c["set_count"] is None
    assert c["item_type"] == "general"                 # 카테고리 상속
    assert "maybe_electronics" in c["flags"]
    assert c["q1"] == "텀블러 500ml"
    assert "q2" not in c                               # 빈 필드 → skip_if_missing


def test_map_missing_goes_to_queue(d):
    r = engine.run(RULES, ctx(d, attrs_raw={"材质": "钛合金"}), d)
    assert r.ctx["material_code"] is None
    assert r.ctx["missing"] == [{"kind": "material", "term": "钛合金"}]


def test_validate_catches_bad_rules():
    errs = engine.validate([{"op": "regex", "from": "x", "pattern": "(", "as": "y"}, {"op": "nope"}, {"op": "map", "kind": "material"}])
    assert any("정규식" in e for e in errs)
    assert any("op" in e for e in errs)
    assert any("누락" in e for e in errs)
    assert engine.validate(RULES) == []


def test_coverage(d):
    samples = [ctx(d), ctx(d, title_raw="保温杯 不锈钢 大容量", attrs_raw={}), ctx(d, title_raw="玻璃杯 350ml", attrs_raw={"材质": "玻璃"})]
    cov = engine.coverage(RULES, samples, d, ["title_clean", "material_code", "q1"])
    assert cov["title_clean"] == 100.0
    assert abs(cov["material_code"] - 66.7) < 0.1
    assert abs(cov["q1"] - 66.7) < 0.1
    assert cov["_errors"] == 0


def test_bad_rule_does_not_stop_run(d):
    rules = [{"op": "regex", "from": "title_raw", "pattern": "(", "as": "x"}, {"op": "strip", "from": "title_raw", "as": "t"}]
    r = engine.run(rules, ctx(d), d)
    assert len(r.errors) == 1 and "t" in r.ctx
