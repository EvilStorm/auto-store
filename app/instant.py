"""URL 즉시 분석 CLI.

  python -m app.instant <상품URL> [--headed] [--profile 1688]
  python -m app.instant --fetch-only <상품URL>      # 페이지 스냅샷만 확인 (LLM·네이버 호출 없음)
  python -m app.instant --recent [N]                # 최근 분석 이력
  python -m app.instant --show <id>                 # 이력 1건의 카드 다시 보기

결과는 data/analyses/<id>.json 에 저장되고 index.jsonl 에 한 줄 요약이 쌓인다.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from app.config import settings

ANALYSES = settings.data_dir / "analyses"
INDEX = ANALYSES / "index.jsonl"


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _today_count() -> int:
    if not INDEX.exists():
        return 0
    today = datetime.now().strftime("%Y%m%d")
    return sum(1 for line in INDEX.read_text(encoding="utf-8").splitlines() if line.startswith('{"id": "' + today))


def _save(record: dict) -> None:
    ANALYSES.mkdir(parents=True, exist_ok=True)
    (ANALYSES / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary = {
        "id": record["id"],
        "requested_at": record["requested_at"],
        "channel": record["channel"],
        "url": record["url"],
        "host": record.get("host"),
        "status": record["status"],
        "title_ko": (record.get("normalized") or {}).get("title_ko"),
        "margin_rate": (record.get("economics") or {}).get("margin_rate"),
        "score": (record.get("economics") or {}).get("score"),
        "exact_count": (record.get("match") or {}).get("exact_count"),
        "requirement": (record.get("normalized") or {}).get("requirement_status"),
        "brand_detected": (record.get("normalized") or {}).get("brand_detected"),
        "decision": record.get("decision", "none"),
        "error": record.get("error"),
    }
    with INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


def analyze(url: str, *, channel: str = "cli", headed: bool = False, profile: str | None = None, fetch_only: bool = False) -> dict:
    from app.sources.fetch import fetch_page

    rec: dict = {"id": _new_id(), "requested_at": datetime.now().isoformat(timespec="seconds"), "channel": channel, "url": url, "status": "running"}
    if not fetch_only and _today_count() >= settings.instant_daily_limit:
        rec.update(status="failed", error=f"오늘 즉시 분석 상한({settings.instant_daily_limit}건) 도달")
        _save(rec)
        return rec
    try:
        profile_dir = (settings.profiles_dir / profile) if profile else None
        snap = fetch_page(url, profile_dir=profile_dir, headed=headed)
        rec["host"] = snap.host
        rec["snapshot"] = {
            "final_url": snap.final_url,
            "title": snap.title,
            "text_chars": len(snap.text),
            "text_head": snap.text[:1500],
            "images": snap.images[:8],
            "og_image": snap.og_image,
            "blocked_hint": snap.blocked_hint,
        }
        if fetch_only:
            rec["status"] = "fetched"
            return rec
        if snap.blocked_hint and (len(snap.text) < 200 or "없음" in snap.blocked_hint or "리다이렉트" in snap.blocked_hint):
            rec.update(status="failed", error=f"페이지를 읽지 못함: {snap.blocked_hint}")
            _save(rec)
            return rec

        from app.adapters.exchange_rate import get_rates
        from app.adapters.llm import get_llm
        from app.pipeline.card import render_card
        from app.pipeline.cost import compute
        from app.pipeline.extract import extract_raw, normalize
        from app.pipeline.match import run_match

        llm = get_llm()
        raw = extract_raw(llm, snap)
        rec["raw"] = raw.model_dump()
        if not raw.is_product_page:
            rec.update(status="failed", error=f"상품 페이지가 아님: {raw.page_problem}")
            _save(rec)
            return rec
        norm = normalize(llm, raw, snap)
        rec["normalized"] = norm.model_dump()
        match = run_match(llm, raw, norm, snap.main_image())
        rec["match"] = match.model_dump()
        rates = get_rates()
        rec["rates"] = {"source": rates.source, "fetched_at": rates.fetched_at, "rates": rates.rates}
        econ = compute(raw, norm, match, rates)
        rec["economics"] = econ.model_dump()
        rec["llm_usage"] = [u.__dict__ for u in llm.usage]
        rec["card"] = render_card(url, snap.host, raw, norm, match, econ, llm_cost_krw=llm.total_cost_krw())
        rec["status"] = "done"
    except Exception as e:  # 이력에 실패 사유를 남긴다
        rec.update(status="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])
    _save(rec)
    return rec


def recent(n: int = 10) -> list[dict]:
    if not INDEX.exists():
        return []
    lines = INDEX.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines[-n:]][::-1]


def show(aid: str) -> dict | None:
    p = ANALYSES / f"{aid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main(argv=None) -> int:
    # Windows 콘솔(cp949)에서 한글 출력 깨짐 방지
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="URL 즉시 분석")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--headed", action="store_true", help="브라우저 창을 띄워서 수집 (로그인 저장용)")
    ap.add_argument("--profile", help="로그인 프로필 이름 (예: 1688). data/profiles/<이름> 에 저장")
    ap.add_argument("--fetch-only", action="store_true", help="페이지 스냅샷만 출력")
    ap.add_argument("--recent", nargs="?", const=10, type=int, help="최근 이력 N건")
    ap.add_argument("--show", help="이력 id 의 카드 다시 보기")
    a = ap.parse_args(argv)

    if a.recent is not None:
        rows = recent(a.recent)
        if not rows:
            print("이력이 없습니다.")
            return 0
        for r in rows:
            m = f"{r['margin_rate'] * 100:.0f}%" if r.get("margin_rate") is not None else "-"
            print(f"{r['id']}  {r['status']:<7} {r.get('host') or '':<22} 마진 {m:>5}  점수 {r.get('score') or '-':<6} 정확 {r.get('exact_count') if r.get('exact_count') is not None else '-'}  {r.get('title_ko') or r.get('error') or ''}")
        return 0
    if a.show:
        rec = show(a.show)
        if not rec:
            print("해당 id 가 없습니다.")
            return 1
        print(rec.get("card") or json.dumps(rec, ensure_ascii=False, indent=2))
        return 0
    if not a.url:
        ap.print_help()
        return 1

    rec = analyze(a.url, headed=a.headed, profile=a.profile, fetch_only=a.fetch_only)
    if a.fetch_only:
        print(json.dumps(rec["snapshot"], ensure_ascii=False, indent=2))
        return 0
    if rec["status"] == "done":
        print(rec["card"])
        print(f"\n저장: data/analyses/{rec['id']}.json")
        return 0
    print(f"실패: {rec.get('error')}")
    if rec.get("trace"):
        print(rec["trace"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
