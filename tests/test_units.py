from app.taxonomy import units


def test_capacity_variants():
    n = units.extract_numbers("不锈钢保温杯 500ml 大容量 1.2L 带手柄 40oz")
    assert n["capacity_ml"][0] == 500.0
    assert 1200.0 in n["capacity_ml"]
    assert any(abs(v - 1182.9) < 1 for v in n["capacity_ml"])


def test_length_and_dims():
    n = units.extract_numbers("收纳箱 30*20*10cm 加厚 25厘米")
    assert n["dims_mm"][0] == [300.0, 200.0, 100.0]
    assert 250.0 in n["length_mm"]


def test_weight_and_pack():
    n = units.extract_numbers("硅胶折叠碗 2个装 350g 0.5kg")
    assert n["pack_count"] == [2.0]
    assert 350.0 in n["weight_g"] and 500.0 in n["weight_g"]


def test_no_false_positive_on_letters():
    # 'L' 이 단어 안에 있으면 리터로 잡지 않는다
    n = units.extract_numbers("LED 灯 3W USB 5V")
    assert "capacity_ml" not in n
    assert n["power_w"] == [3.0]


def test_format_and_agree():
    assert units.format_capacity(1200.0) == "1.2L"
    assert units.format_capacity(500.0) == "500ml"
    a = units.extract_numbers("保温杯 500ml")
    b = units.extract_numbers("텀블러 510ml")
    c = units.extract_numbers("텀블러 750ml")
    assert units.numbers_agree(a, b, "capacity_ml") is True
    assert units.numbers_agree(a, c, "capacity_ml") is False
    assert units.numbers_agree(a, {}, "capacity_ml") is None
