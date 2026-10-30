"""환경 설정. .env 를 읽고, 관리자 화면 저장값이 생기면 그 값이 우선하도록 settings 계층을 둔다(지금은 .env만)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _f(key: str, default: float) -> float:
    v = os.getenv(key)
    return float(v) if v not in (None, "") else default


def _i(key: str, default: int) -> int:
    v = os.getenv(key)
    return int(v) if v not in (None, "") else default


def _s(key: str, default: str = "") -> str:
    return os.getenv(key) or default


@dataclass
class Settings:
    # AI
    llm_provider: str = field(default_factory=lambda: _s("LLM_PROVIDER", "claude"))
    llm_model: str = field(default_factory=lambda: _s("LLM_MODEL", ""))
    anthropic_api_key: str = field(default_factory=lambda: _s("ANTHROPIC_API_KEY"))
    google_ai_api_key: str = field(default_factory=lambda: _s("GOOGLE_AI_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _s("OPENAI_API_KEY"))

    # 네이버
    naver_client_id: str = field(default_factory=lambda: _s("NAVER_CLIENT_ID"))
    naver_client_secret: str = field(default_factory=lambda: _s("NAVER_CLIENT_SECRET"))

    # 환율
    eximbank_api_key: str = field(default_factory=lambda: _s("EXIMBANK_API_KEY"))

    # 비용 기본값 (관리자 설정으로 옮겨갈 값들)
    proxy_fee_rate: float = field(default_factory=lambda: _f("PROXY_FEE_RATE", 0.05))
    local_shipping_cny: float = field(default_factory=lambda: _f("LOCAL_SHIPPING_CNY", 8.0))
    customs_duty_rate: float = field(default_factory=lambda: _f("CUSTOMS_DUTY_RATE", 0.08))
    vat_rate: float = field(default_factory=lambda: _f("VAT_RATE", 0.10))
    customs_limit_usd: float = field(default_factory=lambda: _f("CUSTOMS_LIMIT_USD", 150.0))
    customs_warn_usd: float = field(default_factory=lambda: _f("CUSTOMS_WARN_USD", 130.0))
    naver_fee_rate: float = field(default_factory=lambda: _f("NAVER_FEE_RATE", 0.055))
    payment_fee_rate: float = field(default_factory=lambda: _f("PAYMENT_FEE_RATE", 0.02))
    fx_buffer_rate: float = field(default_factory=lambda: _f("FX_BUFFER_RATE", 0.02))
    target_margin_rate: float = field(default_factory=lambda: _f("TARGET_MARGIN_RATE", 0.30))

    # 매칭
    naver_top_n: int = field(default_factory=lambda: _i("NAVER_TOP_N", 10))
    price_basis: str = field(default_factory=lambda: _s("PRICE_BASIS", "mean"))  # mean | median | min
    same_image_seller_cap: int = field(default_factory=lambda: _i("SAME_IMAGE_SELLER_CAP", 5))

    # 즉시 분석
    instant_daily_limit: int = field(default_factory=lambda: _i("INSTANT_ANALYSIS_DAILY_LIMIT", 50))

    # 경로
    data_dir: Path = field(default_factory=lambda: ROOT / _s("DATA_DIR", "./data"))
    profiles_dir: Path = field(default_factory=lambda: ROOT / _s("BROWSER_PROFILES_DIR", "./data/profiles"))

    def forwarder_rate_table(self) -> list[tuple[float, int]]:
        """(kg 이하, 원) 구간 요율표. 환경변수 FORWARDER_RATES="0.5:6000,1:7500,..." 로 덮어쓸 수 있다."""
        raw = _s("FORWARDER_RATES")
        if raw:
            out = []
            for part in raw.split(","):
                kg, won = part.split(":")
                out.append((float(kg), int(won)))
            return sorted(out)
        return [(0.5, 6000), (1.0, 7500), (1.5, 9000), (2.0, 10500), (3.0, 13500), (5.0, 19500), (10.0, 34500)]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
