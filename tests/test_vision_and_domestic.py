import math

from app.pipeline import domestic
from app.vision import clip, phash


def test_phash_int64_roundtrip_and_hamming():
    h = "ffffffffffffffff"
    i = phash.to_int64(h)
    assert i == -1 and phash.from_int64(i) == h
    assert phash.hamming("0000000000000000", "0000000000000003") == 2
    assert phash.hamming(phash.to_int64("f000000000000000"), "f000000000000001") == 1
    assert phash.same_image("abcdef0123456789", "abcdef0123456789")
    assert not phash.same_image("0000000000000000", "ffffffffffffffff")
    assert phash.hamming(None, "00") is None


def test_cosine_and_pgvector():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    c = [0.0, 1.0, 0.0]
    assert abs(clip.cosine(a, b) - 1.0) < 1e-9
    assert abs(clip.cosine(a, c)) < 1e-9
    assert clip.cosine(None, a) is None
    s = clip.to_pgvector([0.5, -0.25])
    assert s == "[0.500000,-0.250000]"
    assert clip.from_pgvector(s) == [0.5, -0.25]


def _vec(angle_deg):
    r = math.radians(angle_deg)
    return [math.cos(r), math.sin(r)]


def test_judge_with_clip_and_numbers():
    src = _vec(0)
    src_numbers = {"capacity_ml": [500.0]}
    cands = [
        domestic.Candidate("a", "스테인리스 텀블러 500ml", 20000, mall="A", clip=_vec(10), review_count=100, cat_id="c1"),   # cos≈0.985 → exact
        domestic.Candidate("b", "텀블러 1L 대용량", 25000, mall="B", clip=_vec(12), review_count=10, cat_id="c1"),             # exact but 용량 불일치 → similar
        domestic.Candidate("c", "텀블러 손잡이", 15000, mall="C", clip=_vec(30), cat_id="c2"),                                   # cos≈0.866 → similar
        domestic.Candidate("d", "다른 상품", 9000, mall="D", clip=_vec(80)),                                                       # unrelated
        domestic.Candidate("ad", "광고", 1000, mall="X", clip=_vec(0), is_ad=True),                                                # 광고 제외
    ]
    j = domestic.judge(src, None, src_numbers, cands)
    assert [r["nv_mid"] for r in j.exact] == ["a"]
    assert sorted(r["nv_mid"] for r in j.similar) == ["b", "c"]
    assert [r["nv_mid"] for r in j.unrelated] == ["d"] and "임계값 미만" in j.unrelated[0]["reason"]   # 광고는 아예 제외
    assert "용량 불일치" in next(r for r in j.similar if r["nv_mid"] == "b")["reason"]
    s = j.signals()
    assert s["exact_count"] == 1 and s["similar_count"] == 2 and s["total_results"] == 5
    assert s["price_mean"] == 20000 and s["basis_type"] == "exact" and s["naver_cat_id"] == "c1" and s["review_top"] == 100


def test_judge_without_clip_uses_phash_and_numbers():
    src_ph = "aaaaaaaaaaaaaaaa"
    cands = [
        domestic.Candidate("same", "텀블러", 10000, mall="M1", phash="aaaaaaaaaaaaaaab"),          # 동일 사진 → exact
        domestic.Candidate("same2", "텀블러 500ml", 11000, mall="M2", phash="aaaaaaaaaaaaaaaa"),   # 동일 사진 → exact
        domestic.Candidate("num", "텀블러 500ml", 12000, mall="M3", phash="0000000000000000"),     # 숫자 일치 → similar
        domestic.Candidate("none", "텀블러 1L", 13000, mall="M4", phash="0000000000000000"),       # 아무것도 → 제외
    ]
    j = domestic.judge(None, src_ph, {"capacity_ml": [500.0]}, cands)
    assert sorted(r["nv_mid"] for r in j.exact) == ["same", "same2"]
    assert [r["nv_mid"] for r in j.similar] == ["num"]
    assert j.same_image_sellers == 2


def test_signals_fallback_to_similar_basis():
    j = domestic.Judgement(similar=[{"price": 1000, "nv_mid": "x"}, {"price": 3000, "nv_mid": "y"}], total=2)
    s = j.signals()
    assert s["basis_type"] == "similar" and s["price_mean"] == 2000 and s["price_median"] == 2000 and s["price_min"] == 1000
