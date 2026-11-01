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
PENDING_REVISE: dict[str, int] = {}   # chat_id → candidate_id (수정 메모를 기다리는 중)


def decide2(c, user_id: str, cid: int, action: str, bot) -> str:
    """2차 카드 [등록 패키지 생성][수정 요청][폐기]."""
    now = datetime.now(timezone.utc).isoformat()
    rows = c.table("candidates").select("*").eq("id", cid).limit(1).execute().data
    if not rows:
        return "후보가 없습니다"
    cand = rows[0]
    if action == "package":
        from app.pipeline import package

        c.table("candidates").update({"status": "approved_2", "decision": "approve2", "decided_at": now}).eq("id", cid).execute()
        cand["status"] = "approved_2"
        try:
            r = package.build(c, user_id, cand)
            bot.send_text(f"패키지 생성 완료 #{cid} · 이미지 {r['images']}장 업로드 · 엑셀 {r['xlsx']}\n판매가 {r['row']['판매가']:,}원 · 상품명 {r['row']['상품명']}")
            return "패키지 생성"
        except Exception as e:
            bot.send_text(f"패키지 생성 실패 #{cid}: {type(e).__name__}: {str(e)[:200]}")
            return "패키지 실패"
    if action == "revise":
        c.table("candidates").update({"status": "revise", "decision": "revise", "decided_at": now}).eq("id", cid).execute()
        PENDING_REVISE[str(bot.chat_id)] = cid
        bot.send_text(f"#{cid} 수정 메모를 답장으로 보내주세요 (예: 제목을 더 짧게, 옵션 색상명 통일). 받으면 다시 생성합니다.")
        return "수정 메모 대기"
    if action == "discard":
        c.table("candidates").update({"status": "rejected_2", "decision": "discard", "decided_at": now}).eq("id", cid).execute()
        it = c.table("source_items").select("source_id, source_item_id").eq("id", cand["source_item_id"]).limit(1).execute().data
        if it:
            c.table("rejections").insert({"user_id": user_id, "source_id": it[0]["source_id"], "source_item_id": it[0]["source_item_id"], "reason": "other"}).execute()
        return "폐기"
    return "알 수 없는 동작"


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
    msg = cb.get("message") or {}
    if kind == "p":
        label = decide2(c, user_id, cid, action, bot)
        if msg.get("message_id"):
            bot.edit_buttons(msg["message_id"], [[(f"✓ {label}", f"p:{cid}:done")]])
        return label
    if kind != "c" or action not in ACTIONS:
        return "알 수 없는 버튼"
    label = decide(c, user_id, cid, action)
    if msg.get("message_id"):
        bot.edit_buttons(msg["message_id"], [[(f"✓ {label}", f"c:{cid}:done")]])
    if action == "approve":
        # 승인 즉시 ⑥⑦⑧: 상세 수집 → 콘텐츠 생성(LLM) → 2차 카드 (보통 1~2분)
        bot.send_text(f"#{cid} 승인 → 상세 수집 · 콘텐츠 생성 중 (1~2분)")
        try:
            from app.pipeline import content

            r = content.run(c, user_id, only=cid, bot=bot)
            if r["errors"]:
                bot.send_text("콘텐츠 생성 실패: " + r["errors"][0][:300])
        except Exception as e:
            bot.send_text(f"콘텐츠 생성 오류: {type(e).__name__}: {str(e)[:200]}")
    return label


def handle_message(c, user_id: str, m: dict, bot) -> None:
    text = m.get("text") or ""
    chat = str((m.get("chat") or {}).get("id") or "")
    if chat in PENDING_REVISE and text and not text.startswith("/") and not URL_RE.search(text):
        cid = PENDING_REVISE.pop(chat)
        c.table("generated_contents").update({"revise_note": text[:500]}).eq("candidate_id", cid).execute()
        bot.send_text(f"#{cid} 수정 메모 접수 → 다시 생성 중")
        try:
            from app.pipeline import content

            r = content.run(c, user_id, only=cid, bot=bot)
            if r["errors"]:
                bot.send_text("재생성 실패: " + r["errors"][0][:300])
        except Exception as e:
            bot.send_text(f"재생성 오류: {type(e).__name__}: {str(e)[:200]}")
        return
    urls = URL_RE.findall(text)
    if urls:
        from app.instant import process_queue

        for u in urls[:5]:
            c.table("analysis_requests").insert({"user_id": user_id, "channel": "telegram", "url": u, "status": "queued"}).execute()
        bot.send_text(f"URL {len(urls[:5])}건 접수 → 분석 중 (보통 1~2분)")
        try:
            process_queue(c, user_id, limit=len(urls[:5]), bot=bot)
        except Exception as e:
            bot.send_text(f"즉시 분석 오류: {type(e).__name__}: {str(e)[:200]}")
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
