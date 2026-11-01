from app.sources import s1688


def test_parse_price_range_and_moq():
    raw, tiers = s1688.parse_price("跨境 保温杯 ¥12.50-15.00 2件起批 成交1.2万件")
    assert raw.startswith("¥12.50")
    assert tiers == [{"min_qty": 1, "unit_price": 12.5}]
    assert s1688.parse_moq("2件起批") == 2
    assert s1688.parse_sales("成交1.2万件") == 12000


def test_parse_multi_tier():
    _, tiers = s1688.parse_price("≥2件 ¥12.5 ≥10件 ¥11.8 ≥100件 ¥10.9")
    assert tiers == [{"min_qty": 2, "unit_price": 12.5}, {"min_qty": 10, "unit_price": 11.8}, {"min_qty": 100, "unit_price": 10.9}]


def test_card_to_listing_cleans_image_suffix():
    li = s1688.card_to_listing({
        "id": "6912345678", "href": "https://detail.1688.com/offer/6912345678.html",
        "text": "304不锈钢保温杯 500ml ¥18.5 2件起批 成交300件 回头率 25%",
        "img": "https://cbu01.alicdn.com/img/ibank/abc.jpg_300x300q75.jpg_.webp", "titles": ["永康市梦微五金制品厂", "304不锈钢保温杯 500ml 大容量"],
    })
    assert li is not None
    assert li.title_raw == "304不锈钢保温杯 500ml 大容量"          # 회사명이 아니라 상품명
    assert li.item_id == "6912345678" and li.moq == 2 and li.price_tiers[0]["unit_price"] == 18.5
    assert li.image_url == "https://cbu01.alicdn.com/img/ibank/abc.jpg"
    assert li.extra == {"company": "永康市梦微五金制品厂", "sales": 300, "repeat_rate": 25.0}
    row = li.to_row()
    assert row["source_item_id"] == "6912345678" and row["last_price_src"] == 18.5


def test_pick_title_skips_company_and_price_lines():
    title, company = s1688.pick_title(["东阳市汪物宠物用品有限公司", "¥ 9", "成交1.2万件", "宠物自动饮水机 大容量 不锈钢"], "")
    assert title == "宠物自动饮水机 大容量 不锈钢" and company == "东阳市汪物宠物用品有限公司"
    # 후보가 전부 회사명/가격이면 카드 텍스트의 가격 앞부분
    title2, _ = s1688.pick_title(["永康市司雨五金制品厂"], "304不锈钢保温杯 ¥12 1件起批")
    assert title2 == "304不锈钢保温杯"
    assert s1688.is_company_name("繁昌区呗呗叮叮商行") and not s1688.is_company_name("保温杯 500ml 厂家直销款")


def test_real_search_card_layout():
    # 2026-11-01 실제 1688 검색 카드 텍스트: 상품명은 공백 없는 첫 토큰, 가격은 "¥ 5 .9", 판매량은 "全网4.8万+件"
    text = "家用316不锈钢水杯女高颜值浮球保温杯学生提绳吸管杯大容量杯子 下单返拿样费 ｜ 商机组货：茶杯保温杯 ¥ 5 .9 红包价 全网4.8万+件 包邮 退货包运费 先采后付 回头率54% 永康市舒响工贸有限公司"
    li = s1688.card_to_listing({"id": "953468495242", "href": "https://detail.1688.com/offer/953468495242.html", "text": text, "img": "",
                                "titles": [text, "永康市舒响工贸有限公司", "点此可以直接和卖家交流选好的宝贝，或相互交流网购体验，还支持语音视频噢。", "商机组货：茶杯保温杯", "全网4.8万+件"]})
    assert li.title_raw == "家用316不锈钢水杯女高颜值浮球保温杯学生提绳吸管杯大容量杯子"
    assert li.price_tiers == [{"min_qty": 1, "unit_price": 5.9}] and li.price_raw == "¥ 5 .9"
    assert li.extra["company"] == "永康市舒响工贸有限公司" and li.extra["sales"] == 48000 and li.extra["tags"] == ["茶杯保温杯"]
    assert li.extra["price_label"] == "红包价" and li.extra["free_shipping"] is True and li.extra["repeat_rate"] == 54.0
    assert s1688.parse_price("¥ 0 .68 红包价")[1][0]["unit_price"] == 0.68
    assert s1688.parse_sales("800+件 包邮") == 800 and s1688.parse_sales("10万+件") == 100000 and s1688.parse_sales("全网1.6万+件") == 16000


def test_card_without_price_is_skipped():
    assert s1688.card_to_listing({"id": "1", "href": "h", "text": "no price here", "img": "", "title": ""}) is None


def test_page_url():
    assert s1688.page_url("https://s.1688.com/selloffer/offer_search.htm?keywords=%E4%BF%9D%E6%B8%A9%E6%9D%AF", 3).endswith("beginPage=3")
    assert s1688.page_url("https://example.1688.com/list.html?page=1&x=y", 2) == "https://example.1688.com/list.html?page=2&x=y"
    assert s1688.page_url("https://x/list", 1) == "https://x/list"
