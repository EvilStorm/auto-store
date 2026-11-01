"""텔레그램 콜백 폴러 — [승인][거절][보류] 를 candidates 에 반영. 같은 계정 PC 둘이면 worker_leases 임대를 가진 PC 만 폴링.

  python -m app.telegram_poll            # 계속 돈다 (Ctrl+C 로 종료)
  python -m app.telegram_poll --once     # 쌓인 업데이트만 처리하고 종료

URL 메시지(http…)는 analysis_requests 에 queued 로 넣는다 (즉시 분석은 7단계에서 처리).
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone

from app.adapters.telegram import bot_from, parse_callback
from app.db import current_user_id, pc_name, user_client

ACTIONS = {"approve": ("approved_1", "approve", "승인 → 상세 수집 대기"), "reject": ("rejected_1", "reject", "거절 (90일 제외)"), "hold": ("held", "hold", "보류 → 내일 다시")}
URL_RE = re.compile(r"https?://\S+")


def decide(c, user_id: str, cid: int, action: str) -> str:
    """[승인][거절][보류] 를 candidates 에 반영 (텔레그램 · 관리자 웹 공용). 반환: 사람용 라벨."""
    if action not in ACTIONS:
        return "알 수 없는 동작"
    status, decision, label = ACTIONS[action]
    now = datetime.now(timezone.utc).isoformat()
    rows = c.table("candidates").select("id, status, source_item_id").eq("id", cid).limit(1).execute().data
    if not rows:
        return "후보가 없습니다"
    c.table("candidates").update({"status": status, "decision": decision, "decided_at": now}).eq("id", cid).execute()
    if action == "reject":
        it = c.table("source_items").select("source_id, source_item_id").eq("id", rows[0]["source_item_id"]).limit(1).execute().data
        if it:
            c.table("rejections").insert({"user_id": user_id, "source_id": it[0]["source_id"], "source_item_id": it[0]["source_item_id"], "reason": "quality"}).execute()
    return label


def handle_callback(c, user_id: str, cb: dict, bot) -> str:
    parsed = parse_callback(cb.get("data", ""))
    if not parsed:
        return "알 수 없는 버튼"
    kind, cid, action = parsed
    if kind != "c" or action not in ACTIONS:
        return "알 수 없는 버튼"
    label = decide(c, user_id, cid, action)
    msg = cb.get("message") or {}
    if msg.get("message_id"):
        bot.edit_buttons(msg["message_id"], [[(f"✓ {label}", f"c:{cid}:done")]])
    return label


def handle_message(c, user_id: str, m: dict, bot) -> None:
    text = m.get("text") or ""
    urls = URL_RE.findall(text)
    if urls:
        for u in urls[:5]:
            c.table("analysis_requests").insert({"user_id": user_id, "channel": "telegram", "url": u, "status": "queued"}).execute()
        bot.send_text(f"URL {len(urls[:5])}건 접수 → 즉시 분석 큐 (7단계에서 처리)")
    elif text.startswith("/recent"):
        n = int(text.split()[1]) if len(text.split()) > 1 and text.split()[1].isdigit() else 10
        rows = c.table("candidates").select("run_date, status, margin_rate, score, source_item_id").order("created_at", desc=True).limit(n).execute().data
        bot.send_text("\n".join(f"{r['run_date']} {r['status']:<11} 마진 {(r['margin_rate'] or 0) * 100:.0f}% 점수 {r['score'] or '-'} #{r['source_item_id']}" for r in rows) or "이력 없음")


def loop(once: bool = False) -> int:
    c = user_client()
    uid = current_user_id(c)
    bot = bot_from(c)
    me = pc_name()
    offset = None
    print(f"폴링 시작 · {bot.me().get('username')} · PC {me}")
    while True:
        lease = c.rpc("renew_worker_lease", {"p_kind": "telegram", "p_pc_name": me, "p_ttl_seconds": 90}).execute().data
        if not lease:
            print("다른 PC 가 폴링 임대를 가지고 있습니다 — 60초 뒤 재시도")
            if once:
                return 3
            time.sleep(60)
            continue
        try:
            updates = bot.get_updates(offset, timeout=25)
        except RuntimeError as e:
            print("!", e)
            time.sleep(10)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            if "callback_query" in u:
                cb = u["callback_query"]
                label = handle_callback(c, uid, cb, bot)
                bot.answer_callback(cb["id"], label)
            elif "message" in u:
                handle_message(c, uid, u["message"], bot)
        if once:
            return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    try:
        return loop(once=a.once)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
