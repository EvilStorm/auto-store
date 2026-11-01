"""환율 어댑터. 수동 입력 없음.

우선순위: 1) 한국수출입은행 API (키 필요)  2) 네이버 금융 시장지표 크롤링  3) open.er-api.com (키 없음)  4) 마지막 성공값
저장: 공용 Supabase exchange_rates(하루 1행/통화, 로그인 클라이언트가 있을 때) + 로컬 캐시 data/exchange_rates.json.
JPY 는 100엔 기준 고시를 1엔 기준으로 바꿔 저장한다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from app.config import settings

CURRENCIES = ("CNY", "JPY", "USD")
EXIM_URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
NAVER_URL = "https://finance.naver.com/marketindex/"
ER_API_URL = "https://open.er-api.com/v6/latest/USD"
STALE_HOURS = 48


@dataclass
class Rates:
    rates: dict  # {"CNY": 193.2, "JPY": 9.15, "USD": 1392.0}  (1단위당 원)
    source: str
    fetched_at: str

    def is_stale(self) -> bool:
        t = datetime.fromisoformat(self.fetched_at.replace("Z", "+00:00"))
        now = datetime.now(t.tzinfo) if t.tzinfo else datetime.now()
        return now - t > timedelta(hours=STALE_HOURS)


def _cache_path():
    return settings.data_dir / "exchange_rates.json"


def _save(r: Rates) -> None:
    _cache_path().write_text(json.dumps(asdict(r), ensure_ascii=False, indent=2), encoding="utf-8")


def _load() -> Rates | None:
    p = _cache_path()
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return Rates(**d)


def _num(s: str) -> float:
    return float(s.replace(",", "").strip())


def _from_eximbank() -> Rates | None:
    if not settings.eximbank_api_key:
        return None
    # 영업일이 아니면 빈 배열이 와서 며칠 전까지 거슬러 본다
    for back in range(0, 5):
        day = (datetime.now() - timedelta(days=back)).strftime("%Y%m%d")
        r = httpx.get(EXIM_URL, params={"authkey": settings.eximbank_api_key, "searchdate": day, "data": "AP01"}, timeout=15.0)
        if r.status_code != 200:
            continue
        rows = r.json() or []
        out = {}
        for row in rows:
            unit = row.get("cur_unit", "")
            rate = _num(row.get("deal_bas_r", "0"))
            if unit == "CNH" or unit == "CNY":
                out["CNY"] = rate
            elif unit == "JPY(100)":
                out["JPY"] = rate / 100.0
            elif unit == "USD":
                out["USD"] = rate
        if all(c in out for c in CURRENCIES):
            return Rates(out, "eximbank_api", datetime.now().isoformat(timespec="seconds"))
    return None


def _from_naver_finance() -> Rates | None:
    """네이버 금융 시장지표 첫 화면의 환율 4종(미국 USD · 일본 JPY(100엔) · 유럽 EUR · 중국 CNY) 크롤링."""
    r = httpx.get(NAVER_URL, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")
    out = {}
    for li in soup.select("#exchangeList li"):
        name = li.select_one(".h_lst")
        val = li.select_one(".value")
        if not name or not val:
            continue
        label = name.get_text(" ", strip=True)
        rate = _num(val.get_text())
        if "CNY" in label:
            out["CNY"] = rate
        elif "JPY" in label:
            out["JPY"] = rate / 100.0
        elif "USD" in label:
            out["USD"] = rate
    if all(c in out for c in CURRENCIES):
        return Rates(out, "naver_finance", datetime.now().isoformat(timespec="seconds"))
    return None


def _from_er_api() -> Rates | None:
    """키 없는 공개 환율 API (open.er-api.com). USD 기준 교차환율로 CNY·JPY 를 원화로 환산."""
    r = httpx.get(ER_API_URL, timeout=15.0)
    r.raise_for_status()
    d = r.json()
    if d.get("result") != "success":
        return None
    rates = d["rates"]
    krw = float(rates["KRW"])
    out = {"USD": krw, "CNY": krw / float(rates["CNY"]), "JPY": krw / float(rates["JPY"])}
    return Rates({k: round(v, 4) for k, v in out.items()}, "open_er_api", datetime.now().isoformat(timespec="seconds"))


# ── 공용 테이블 (v3) ──
def _from_db(client) -> Rates | None:
    try:
        rows = client.rpc("latest_exchange_rates").execute().data or []
    except Exception:
        return None
    out = {r["currency"]: float(r["rate_krw"]) for r in rows}
    if not all(c in out for c in CURRENCIES):
        return None
    oldest = min(r["fetched_at"] for r in rows if r["currency"] in CURRENCIES)
    return Rates(out, rows[0]["source"], oldest)


def _to_db(client, r: Rates) -> None:
    try:
        now = datetime.now(timezone.utc).isoformat()
        client.table("exchange_rates").insert(
            [{"currency": k, "rate_krw": v, "source": r.source, "fetched_at": now} for k, v in r.rates.items() if k in CURRENCIES]
        ).execute()
    except Exception:
        pass


def get_rates(force_refresh: bool = False, client=None) -> Rates:
    """client(로그인) 가 있으면 공용 테이블을 먼저 보고, 신선한 행이 없을 때만 외부에서 받아 공용에 쓴다 (DESIGN ⓪)."""
    cached = (_from_db(client) if client is not None else None) or _load()
    if cached and not force_refresh and not cached.is_stale():
        return cached
    for fn in (_from_eximbank, _from_naver_finance, _from_er_api):
        try:
            r = fn()
        except Exception:
            r = None
        if r:
            if client is not None:
                _to_db(client, r)
            try:
                _save(r)
            except Exception:
                pass
            return r
    if cached:
        return Rates(cached.rates, "last_known", cached.fetched_at)
    # 아무 것도 없을 때의 최후 값 (경고와 함께 사용)
    return Rates({"CNY": 195.0, "JPY": 9.2, "USD": 1400.0}, "fallback_constant", datetime(2000, 1, 1).isoformat())


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    r = get_rates(force_refresh="--refresh" in sys.argv)
    print(f"source={r.source} fetched_at={r.fetched_at} stale={r.is_stale()}")
    for k, v in r.rates.items():
        print(f"  {k}: {v}")
