"""CLIP 임베딩 (open_clip ViT-B-32, CPU). 설계 6-③: 소스 대표 이미지 vs 네이버 썸네일 유사도.

모델은 첫 호출에 한 번만 로드한다(~350MB 자동 다운로드, HF_HOME/캐시). torch 가 없으면 available() 이 False 이고
파이프라인은 pHash + 속성 규칙만으로 돈다(정밀도는 떨어지지만 멈추지 않는다).
"""
from __future__ import annotations

import math
import os
from typing import Sequence

# 'openai' 가중치는 QuickGELU 로 학습됐으므로 -quickgelu 변형을 써야 경고 없이 정확하다
MODEL_NAME = os.getenv("CLIP_MODEL", "ViT-B-32-quickgelu")
PRETRAINED = os.getenv("CLIP_PRETRAINED", "openai")
DIM = 512

_model = None
_preprocess = None
_torch = None


def available() -> bool:
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401

        return True
    except Exception:
        return False


def _load():
    global _model, _preprocess, _torch
    if _model is not None:
        return
    import open_clip
    import torch

    torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    model.eval()
    _model, _preprocess, _torch = model, preprocess, torch


def embed_images(images: Sequence) -> list[list[float]]:
    """PIL 이미지 목록 → L2 정규화된 512차원 벡터 목록. 빈 입력은 빈 목록."""
    if not images:
        return []
    _load()
    with _torch.no_grad():
        batch = _torch.stack([_preprocess(im.convert("RGB")) for im in images])
        feats = _model.encode_image(batch)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return [[float(x) for x in row] for row in feats.cpu().tolist()]


def embed_bytes(blobs: Sequence[bytes]) -> list[list[float] | None]:
    from app.vision.phash import open_image

    ims, idx = [], []
    for i, b in enumerate(blobs):
        try:
            ims.append(open_image(b))
            idx.append(i)
        except Exception:
            pass
    out: list[list[float] | None] = [None] * len(blobs)
    if ims:
        for i, v in zip(idx, embed_images(ims)):
            out[i] = v
    return out


def cosine(a: Sequence[float] | None, b: Sequence[float] | None) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else None


def to_pgvector(v: Sequence[float]) -> str:
    """supabase-py 로 vector 컬럼에 넣을 때의 문자열 표현 '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def from_pgvector(s) -> list[float] | None:
    if s is None:
        return None
    if isinstance(s, list):
        return [float(x) for x in s]
    try:
        return [float(x) for x in str(s).strip("[]").split(",") if x.strip()]
    except Exception:
        return None
