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
        "img": "https://cbu01.alicdn.com/img/ibank/abc.jpg_300x300q75.jpg_.webp", "title": "304不锈钢保温杯 500ml",
    })
    assert li is not None
    assert li.item_id == "6912345678" and li.moq == 2 and li.price_tiers[0]["unit_price"] == 18.5
    assert li.image_url == "https://cbu01.alicdn.com/img/ibank/abc.jpg"
    assert li.extra == {"sales": 300, "repeat_rate": 25.0}
    row = li.to_row()
    assert row["source_item_id"] == "6912345678" and row["last_price_src"] == 18.5


def test_card_without_price_is_skipped():
    assert s1688.card_to_listing({"id": "1", "href": "h", "text": "no price here", "img": "", "title": ""}) is None


def test_page_url():
    assert s1688.page_url("https://s.1688.com/selloffer/offer_search.htm?keywords=%E4%BF%9D%E6%B8%A9%E6%9D%AF", 3).endswith("beginPage=3")
    assert s1688.page_url("https://example.1688.com/list.html?page=1&x=y", 2) == "https://example.1688.com/list.html?page=2&x=y"
    assert s1688.page_url("https://x/list", 1) == "https://x/list"
