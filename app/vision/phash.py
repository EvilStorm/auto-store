"""이미지 내려받기 · pHash · 해밍 거리.

pHash 는 (1) 동일 사진을 쓰는 국내 판매자 수 (2) AI 결과 캐시의 이미지 키 (3) 거절 이력의 이미지 재등장 차단에 쓴다.
64비트 해시를 Postgres bigint(부호 있는 int64)로 저장하기 위해 to_int64 / from_int64 를 둔다.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HAMMING_SAME = 6  # 이 이하면 같은 사진으로 본다 (리사이즈 · 재압축 허용)


@dataclass
class ImageBytes:
    url: str
    data: bytes
    content_type: str = ""


def fetch(url: str, *, timeout: float = 15.0, referer: str | None = None) -> ImageBytes | None:
    """썸네일 1장 내려받기. 실패하면 None (파이프라인은 그 이미지만 건너뛴다)."""
    if not url:
        return None
    headers = {"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    try:
        r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        if r.status_code != 200 or not r.content:
            return None
        return ImageBytes(url, r.content, r.headers.get("content-type", ""))
    except Exception:
        return None


def open_image(data: bytes):
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    return im


def phash_hex(data: bytes) -> str | None:
    try:
        import imagehash

        return str(imagehash.phash(open_image(data), hash_size=8))  # 16 hex = 64 bit
    except Exception:
        return None


def to_int64(hex_hash: str) -> int:
    v = int(hex_hash, 16)
    return v - (1 << 64) if v >= (1 << 63) else v


def from_int64(v: int) -> str:
    return f"{(v + (1 << 64)) % (1 << 64):016x}"


def hamming(a: str | int | None, b: str | int | None) -> int | None:
    if a is None or b is None:
        return None
    ia = int(a, 16) if isinstance(a, str) else (a + (1 << 64)) % (1 << 64)
    ib = int(b, 16) if isinstance(b, str) else (b + (1 << 64)) % (1 << 64)
    return bin(ia ^ ib).count("1")


def same_image(a, b, threshold: int = HAMMING_SAME) -> bool:
    h = hamming(a, b)
    return h is not None and h <= threshold
