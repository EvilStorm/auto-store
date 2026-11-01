from app import instant


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *a, **k):
        return self

    def execute(self):
        class R:
            pass

        r = R()
        r.data = self.rows
        return r


class FakeClient:
    def __init__(self, sources):
        self._sources = sources

    def table(self, name):
        assert name == "sources"
        return FakeTable(self._sources)


SOURCES = [{"id": "1688", "base_url": "https://www.1688.com", "adapter_key": "1688", "auth_mode": "browser_profile"},
           {"id": "aliexpress", "base_url": "https://ko.aliexpress.com", "adapter_key": "aliexpress", "auth_mode": "none"}]


def test_find_source_by_registrable_domain():
    c = FakeClient(SOURCES)
    assert instant.find_source(c, "https://detail.1688.com/offer/953468495242.html")["id"] == "1688"
    assert instant.find_source(c, "https://www.aliexpress.com/item/1005.html")["id"] == "aliexpress"
    assert instant.find_source(c, "https://www.netsea.jp/shop/1") is None


def test_weight_parse():
    assert instant._weight_g("350g") == 350
    assert instant._weight_g("0.5kg") == 500
    assert instant._weight_g("") is None
