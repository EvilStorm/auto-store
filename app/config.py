"""환경 설정.

APP_ENV(dev | prd, 비우면 dev)에 따라 .env.dev 또는 .env.prd 를 읽는다. 두 파일은 git 에 올라가지 않는다.
  PowerShell:  $env:APP_ENV="prd"; .venv\\Scripts\\python -m app.instant <URL>
  zsh:         APP_ENV=prd .venv/bin/python -m app.instant <URL>
우선순위: OS 환경변수 > .env.{APP_ENV}. 환경 파일이 없을 때만 옛 방식인 .env 를 읽는다(dev 키가 prd 로 새지 않도록 둘을 섞지 않는다).
확인: python -m app.config  (어느 환경 · 어느 파일을 읽었고 어떤 키가 채워졌는지, 값은 보여주지 않음)
관리자 화면 저장값(v3: Supabase user_settings)이 생기면 그 값이 우선하도록 settings 계층을 둔다(지금은 파일만).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENVS = ("dev", "prd")


def _pick_env() -> str:
    env = (os.getenv("APP_ENV") or "dev").strip().lower()
    if env not in ENVS:
        # import 시점에 나는 오류라 CLI 의 utf-8 재설정보다 먼저다. 윈도우 cp949 콘솔에서 한글이 깨지지 않게 여기서 바꾼다
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        raise SystemExit(f"APP_ENV 는 {' | '.join(ENVS)} 중 하나여야 합니다: {env!r}  (예: $env:APP_ENV=\"prd\" 또는 비워서 dev)")
    return env


APP_ENV = _pick_env()
ENV_FILE: Path | None = None
for _candidate in (ROOT / f".env.{APP_ENV}", ROOT / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
        ENV_FILE = _candidate
        break


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
    # 환경
    app_env: str = field(default_factory=lambda: APP_ENV)

    # AI
    llm_provider: str = field(default_factory=lambda: _s("LLM_PROVIDER", "openai"))
    llm_model: str = field(default_factory=lambda: _s("LLM_MODEL", ""))
    anthropic_api_key: str = field(default_factory=lambda: _s("ANTHROPIC_API_KEY"))
    google_ai_api_key: str = field(default_factory=lambda: _s("GOOGLE_AI_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _s("OPENAI_API_KEY"))

    # Supabase (v3: DB · 인증 · 스토리지). service_role 과 DB URL 은 scripts/ 에서만 os.getenv 로 읽는다
    supabase_url: str = field(default_factory=lambda: _s("SUPABASE_URL"))
    supabase_anon_key: str = field(default_factory=lambda: _s("SUPABASE_ANON_KEY"))
    supabase_bucket: str = field(default_factory=lambda: _s("SUPABASE_BUCKET", "product-images"))
    # user_settings 에서 덮어쓴 배대지 요율표 (없으면 .env / 기본값)
    forwarder_rates_override: str = ""

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
    # CLIP 코사인. 2026-11-01 실측(ViT-B-32, 텀블러 5장): 같은 상품 다른 컷 0.61 · 다른 브랜드 카탈로그 컷 0.85 →
    # CLIP 만으로 "정확" 판정은 불가. 0.95 는 거의 동일 사진에만 걸리고, "정확"은 pHash 동일 사진 · LLM 재판정이 맡는다 (DESIGN 11장)
    exact_threshold: float = field(default_factory=lambda: _f("EXACT_THRESHOLD", 0.95))
    similar_threshold: float = field(default_factory=lambda: _f("SIMILAR_THRESHOLD", 0.70))
    naver_cache_ttl_days: int = field(default_factory=lambda: _i("NAVER_CACHE_TTL_DAYS", 7))

    # 후보 · 카드 (개인 설정으로 덮어씀)
    margin_threshold: float = field(default_factory=lambda: _f("MARGIN_THRESHOLD", 0.30))      # 이 미만은 below_margin
    daily_candidate_n: int = field(default_factory=lambda: _i("DAILY_CANDIDATE_LIMIT", 10))   # 카드로 보낼 N
    llm_rejudge_top_n: int = field(default_factory=lambda: _i("LLM_REJUDGE_TOP_N", 10))       # N건 LLM 매칭 재판정 (0 = 끔)
    daily_llm_cap: int = field(default_factory=lambda: _i("DAILY_LLM_CAP", 50))
    monitor_interval_days: int = field(default_factory=lambda: _i("MONITOR_INTERVAL_DAYS", 3))
    monitor_price_threshold: float = field(default_factory=lambda: _f("MONITOR_PRICE_THRESHOLD", 0.05))
    collect_at: str = field(default_factory=lambda: _s("BATCH_COLLECT_AT", "02:00"))
    notify_at: str = field(default_factory=lambda: _s("BATCH_NOTIFY_AT", "08:00"))
    telegram_bot_token: str = field(default_factory=lambda: _s("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _s("TELEGRAM_CHAT_ID"))

    # 즉시 분석
    instant_daily_limit: int = field(default_factory=lambda: _i("INSTANT_ANALYSIS_DAILY_LIMIT", 50))

    # 경로
    data_dir: Path = field(default_factory=lambda: ROOT / _s("DATA_DIR", "./data"))
    profiles_dir: Path = field(default_factory=lambda: ROOT / _s("BROWSER_PROFILES_DIR", "./data/profiles"))

    def forwarder_rate_table(self) -> list[tuple[float, int]]:
        """(kg 이하, 원) 구간 요율표. user_settings.forwarder_rates > 환경변수 FORWARDER_RATES > 기본값."""
        raw = self.forwarder_rates_override or _s("FORWARDER_RATES")
        if raw:
            out = []
            for part in raw.split(","):
                kg, won = part.split(":")
                out.append((float(kg), int(won)))
            return sorted(out)
        return [(0.5, 6000), (1.0, 7500), (1.5, 9000), (2.0, 10500), (3.0, 13500), (5.0, 19500), (10.0, 34500)]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)


# 비밀값은 "채워짐 / 비어 있음" 만 보여준다. SUPABASE_URL 은 어느 프로젝트(dev / prd)인지 구분용으로 값을 보여준다.
_CHECK_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_AI_API_KEY",
    "EXIMBANK_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


def describe() -> str:
    lines = [
        f"APP_ENV={APP_ENV}",
        f"읽은 파일: {ENV_FILE.name if ENV_FILE else '(없음 — .env.' + APP_ENV + ' 를 만드세요: copy .env.example .env.' + APP_ENV + ')'}",
    ]
    for k in _CHECK_KEYS:
        v = (os.getenv(k) or "").strip()
        shown = v if k == "SUPABASE_URL" else ("채워짐" if v else "비어 있음")
        lines.append(f"  {k:<22} {shown}")
    lines.append(f"  LLM_PROVIDER={settings.llm_provider}  LLM_MODEL={settings.llm_model or '(제공자 기본)'}")
    lines.append(f"  DATA_DIR={settings.data_dir}  INSTANT_ANALYSIS_DAILY_LIMIT={settings.instant_daily_limit}")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(describe())
