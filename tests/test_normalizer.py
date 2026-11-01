from app.pipeline import normalizer


def raw(title, attrs=None, cat=""):
    return {"title_raw": title, "attrs_raw": attrs or {}, "category_raw": cat, "price_raw": "¥18.5"}


def test_tumbler_default_rules(d):
    n = normalizer.normalize(raw("跨境爆款 304不锈钢保温杯 500ml 大容量 车载", {"材质": "304不锈钢", "品牌": "无"}), d.categories["kitchen.tumbler"], d)
    assert n.material_code == "stainless"
    assert n.item_type == "general"
    assert n.canonical_category_id == "kitchen.tumbler"
    assert n.search_queries[0] == "텀블러 500ml"
    assert "보온병 스테인리스" in n.search_queries
    assert n.excluded_reason is None and n.requirement_status == "pass"
    assert n.brand_text_hit is None
    assert n.missing == []
    assert n.dict_version == 1


def test_brand_text_excludes(d):
    n = normalizer.normalize(raw("斯坦利 Stanley 保温杯 1.18L", {"品牌": "Stanley"}), d.categories["kitchen.tumbler"], d)
    assert n.brand_text_hit in ("stanley", "斯坦利")
    assert n.excluded_reason == "brand_text"


def test_electronics_flag_promotes_item_type(d):
    n = normalizer.normalize(raw("USB充电 LED 小夜灯 卧室"), d.categories["deco.wall"], d)
    assert n.item_type == "electronics"
    assert n.requirement_status == "required"
    assert n.excluded_reason is None


def test_food_flag_excludes(d):
    n = normalizer.normalize(raw("零食 坚果 混合 500g"), d.categories["kitchen.container"], d)
    assert n.item_type == "food" and n.excluded_reason == "food"


def test_unknown_material_pending(d):
    n = normalizer.normalize(raw("钛合金 保温杯 600ml", {"材质": "钛合金"}), d.categories["kitchen.tumbler"], d)
    assert n.material_code is None
    assert n.missing and n.missing[0]["kind"] == "material"
    assert normalizer.to_row(1, n)["mapping_pending"] is True


def test_category_crumb_conflict_goes_to_queue(d):
    n = normalizer.normalize(raw("收纳箱 大号", cat="收纳箱"), d.categories["kitchen.tumbler"], d)
    assert any(m["kind"] == "category" for m in n.missing)


def test_no_category_uses_crumb(d):
    n = normalizer.normalize(raw("保温杯 500ml", cat="保温杯"), None, d)
    assert n.canonical_category_id == "kitchen.tumbler"
