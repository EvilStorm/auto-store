"""계정별 설정(user_settings) 과 .env 부트스트랩 병합.

첫 로그인 때 user_settings 가 없으면 .env.{APP_ENV} 의 값으로 1행을 만든다. 이후는 DB 값이 진실이고
settings 객체에 덮어쓴다 (DESIGN 7장 "설정값의 출처"). PC 를 바꿔도 같은 값이 나온다.
"""
from __future__ import annotations

from app.config import Settings, settings

# DB 컬럼 ↔ Settings 필드 (이름이 같은 것만 자동 병합)
MERGE_FIELDS = (
    "proxy_fee_rate", "local_shipping_cny", "customs_duty_rate", "vat_rate", "customs_limit_usd", "customs_warn_usd",
    "naver_fee_rate", "payment_fee_rate", "fx_buffer_rate", "target_margin_rate",
    "price_basis", "same_image_seller_cap", "naver_top_n", "instant_daily_limit",
    "exact_threshold", "similar_threshold",
    "llm_provider", "llm_model",
)


def defaults_from_env() -> dict:
    """현재 settings(.env 로드 결과)에서 user_settings 초기 행을 만든다."""
    s = settings
    return {
        "proxy_fee_rate": s.proxy_fee_rate,
        "local_shipping_cny": s.local_shipping_cny,
        "customs_duty_rate": s.customs_duty_rate,
        "vat_rate": s.vat_rate,
        "customs_limit_usd": s.customs_limit_usd,
        "customs_warn_usd": s.customs_warn_usd,
        "naver_fee_rate": s.naver_fee_rate,
        "payment_fee_rate": s.payment_fee_rate,
        "fx_buffer_rate": s.fx_buffer_rate,
        "target_margin_rate": s.target_margin_rate,
        "margin_threshold": s.target_margin_rate,
        "forwarder_rates": ",".join(f"{kg:g}:{won}" for kg, won in s.forwarder_rate_table()),
        "price_basis": s.price_basis,
        "exact_threshold": s.exact_threshold,
        "similar_threshold": s.similar_threshold,
        "same_image_seller_cap": s.same_image_seller_cap,
        "naver_top_n": s.naver_top_n,
        "instant_daily_limit": s.instant_daily_limit,
        "llm_provider": s.llm_provider,
        "llm_model": s.llm_model,
    }


def ensure_user_settings(client, user_id: str) -> tuple[dict, bool]:
    """(설정 행, 방금 생성했는가). 생성 시 .env 기본값을 넣고, 어느 경우든 settings 에 병합한다."""
    rows = client.table("user_settings").select("*").eq("user_id", user_id).limit(1).execute().data
    created = False
    if rows:
        row = rows[0]
    else:
        payload = {"user_id": user_id, **defaults_from_env()}
        row = client.table("user_settings").insert(payload).execute().data[0]
        created = True
    apply_to_settings(row, settings)
    return row, created


def apply_to_settings(row: dict, target: Settings) -> None:
    for k in MERGE_FIELDS:
        if k in row and row[k] is not None:
            cur = getattr(target, k, None)
            v = row[k]
            if isinstance(cur, float):
                v = float(v)
            elif isinstance(cur, int) and not isinstance(cur, bool):
                v = int(v)
            setattr(target, k, v)
    if row.get("forwarder_rates"):
        target.forwarder_rates_override = str(row["forwarder_rates"])
