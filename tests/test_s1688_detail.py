from app.sources import s1688

HTML = (
    '<html><script>window.x={"tempModel":{"offerUnit":"个","offerId":772378028198,"offerTitle":"伴手礼保温杯带提绳304不锈钢真空口袋杯","postCategoryId":1043766,'
    '"companyName":"永康市领歌工贸有限公司"},"mainPrice":{"currentPrices":[{"price":"8.90","beginAmount":1},{"price":"9.50","beginAmount":1},{"price":"7.80","beginAmount":100}]},'
    '"skuInfoMap":{"蓝色&gt;200毫升":{"specId":"a","saleCount":0,"discountPrice":"8.90","canBookCount":82064,"price":"8.90","skuId":1},'
    '"米白色&gt;360毫升":{"specId":"b","saleCount":3,"discountPrice":"9.50","canBookCount":0,"price":"9.50","skuId":2}},'
    '"pieceWeightScaleInfo":[{"sku2":"360毫升","volume":980.0,"sku1":"橙色","length":20.0,"width":7.0,"weight":200,"skuId":1,"height":7.0},{"weight":180,"length":18.0,"width":7.0,"height":7.0}],'
    '"mainImageList":[{"fullPathImageURI":"https://cbu01.alicdn.com/img/ibank/a.jpg"},{"fullPathImageURI":"https://cbu01.alicdn.com/img/ibank/b.jpg"}]}</script></html>'
)
TEXT = "永康市领歌工贸有限公司\n商品属性\n内胆材质\t\n304不锈钢\n\t品牌\t\n领歌\n材质\t\n内304外201\n容量\t\n360毫升,200毫升\n展开全部\n包装信息\n券后\n¥\n0\n.90\n起\n1个起批\n已售8.2万+个\n容量\n360毫升\n¥9.5\n库存52923个\n"


def test_parse_embedded_fields():
    e = s1688.parse_embedded(HTML)
    assert e["title"].startswith("伴手礼保温杯")
    assert e["tiers"] == [{"min_qty": 1, "unit_price": 8.9}, {"min_qty": 100, "unit_price": 7.8}]   # 같은 beginAmount 는 최저가, 구간은 정렬
    assert e["weight_g"] == 200.0 and e["dims_cm"] == [20.0, 7.0, 7.0]
    assert len(e["images"]) == 2 and e["company"] == "永康市领歌工贸有限公司" and e["cat_id"] == "1043766"
    assert len(e["options"]) == 2 and e["options"][1]["sold_out"] is True and e["options"][0]["name_raw"] == "蓝色>200毫升"


def test_parse_attr_text_pairs_two_column_table():
    a = s1688.parse_attr_text(TEXT)
    assert a["内胆材质"] == "304不锈钢" and a["品牌"] == "领歌" and a["材质"] == "内304外201" and a["容量"] == "360毫升,200毫升"
    assert "包装信息" not in a


def test_build_detail_prefers_embedded_and_parses_moq_sales():
    d = s1688.build_detail("https://detail.1688.com/offer/772378028198.html", TEXT, {"imgs": [], "metas": {}, "crumbs": []}, s1688.parse_embedded(HTML))
    assert d.item_id == "772378028198" and d.price_tiers[0]["unit_price"] == 8.9 and d.price_raw == "¥8.9/7.8"
    assert d.moq == 1 and d.weight_raw == "200g" and d.extra["sales"] == 82000 and d.image_url.endswith("a.jpg")
    assert d.attrs_raw["内胆材质"] == "304不锈钢" and len(d.options) == 2 and d.sold_out is False


def test_build_detail_text_fallback_skips_coupon_price():
    d = s1688.build_detail("https://detail.1688.com/offer/1.html", TEXT, {"imgs": [], "metas": {}, "crumbs": []}, {})
    assert d.price_tiers == [{"min_qty": 1, "unit_price": 9.5}]   # '券后 ¥0.90起' 가 아니라 SKU 행의 ¥9.5
