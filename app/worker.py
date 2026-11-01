"""배치 진입점 (DESIGN.md 2장 ⓪~⑤). 잠금을 얻은 PC 한 대가 실행한다.

  python -m app.worker run                     # ⓪ 환율 → ① ② 수집·정규화 → ③ 국내 조회 → ④ 점수 → ⑤ 카드  한 번에
  python -m app.worker run --stage collect|lookup|score|notify
  python -m app.worker schedule                # 개인 설정 collect_at / notify_at 에 맞춰 매일 (APScheduler, 전면 실행)
  python -m app.worker status                  # 오늘 잠금 · 후보 · 마지막 로그
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date

from app import repo
from app.config import settings
from app.db import current_user_id, pc_name, user_client
from app.user_settings import ensure_user_settings

STAGES = ("collect", "lookup", "score", "notify", "content", "package", "monitor")


def run_stages(c, uid: str, stages: tuple[str, ...], *, headed: bool = False, dry_run: bool = False) -> dict:
    out: dict = {}
    today = date.today()
    if "collect" in stages:
        from app.adapters.exchange_rate import get_rates
        from app.pipeline import collector

        out["rates"] = get_rates(client=c).source  # ⓪
        cnt = collector.run(c, dry_run=dry_run, headed=headed, user_id=uid)
        out["collect"] = cnt.as_dict()
        if not dry_run:
            repo.log_run(c, uid, "collect", today, cnt.as_dict(), pc_name=pc_name(), error=(cnt.errors[0] if cnt.errors else None))
    if "lookup" in stages and not dry_run:
        from app.pipeline import domestic

        pairs = domestic.pending_items(c, settings.daily_lookup_cap if hasattr(settings, "daily_lookup_cap") else 300, settings.naver_cache_ttl_days)
        done, errs = 0, []
        for it, nm in pairs:
            try:
                domestic.lookup(c, it, nm, naver_profile_dir=(settings.profiles_dir / "naver") if (settings.profiles_dir / "naver").exists() else None)
                done += 1
            except Exception as e:
                errs.append(f"{it['id']}: {type(e).__name__}: {e}")
        out["lookup"] = {"items": done, "errors": errs[:10]}
        repo.log_run(c, uid, "lookup", today, out["lookup"], pc_name=pc_name())
    if "score" in stages and not dry_run:
        from app.pipeline import scoring

        out["score"] = scoring.run(c, uid)
        repo.log_run(c, uid, "score", today, out["score"], pc_name=pc_name())
    if "notify" in stages and not dry_run:
        from app.pipeline import notify

        r = notify.run(c, uid)
        out["notify"] = {k: v for k, v in r.items() if k != "texts"}
    if "content" in stages and not dry_run:
        from app.pipeline import content

        bot = None
        try:
            from app.adapters.telegram import bot_from

            bot = bot_from(c)
        except Exception:
            pass
        out["content"] = content.run(c, uid, bot=bot, headed=headed)
        repo.log_run(c, uid, "content", today, out["content"], pc_name=pc_name())
    if "package" in stages and not dry_run:
        from app.pipeline import package

        out["package"] = package.run(c, uid)
        repo.log_run(c, uid, "package", today, out["package"], pc_name=pc_name())
    if "monitor" in stages and not dry_run:
        from app.pipeline import monitor

        bot = None
        try:
            from app.adapters.telegram import bot_from

            bot = bot_from(c)
        except Exception:
            pass
        out["monitor"] = monitor.run(c, uid, bot=bot, headed=headed)
        repo.log_run(c, uid, "monitor", today, out["monitor"], pc_name=pc_name())
    return out


def monitor_due(c) -> bool:
    """마지막 감시 로그가 monitor_interval_days 보다 오래됐으면 True (⑩ 은 수집 배치 직후 주기적으로)."""
    from datetime import datetime, timedelta, timezone

    rows = c.table("run_logs").select("started_at").eq("kind", "monitor").order("started_at", desc=True).limit(1).execute().data
    if not rows:
        return True
    last = datetime.fromisoformat(rows[0]["started_at"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - last >= timedelta(days=int(settings.monitor_interval_days))


def cmd_run(a) -> int:
    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    stages = (a.stage,) if a.stage else ("collect", "lookup", "score", "notify")   # 전체 실행은 발굴 ①~⑤. 2차는 승인 콜백 또는 --stage content|package
    if not a.no_lock and not a.dry_run and not repo.acquire_lock(c, date.today(), "batch", pc_name()):
        print("다른 PC 가 오늘 배치 잠금을 가지고 있습니다 (--no-lock 으로 강제)")
        return 3
    try:
        out = run_stages(c, uid, stages, headed=a.headed, dry_run=a.dry_run)
    except Exception as e:
        print(f"실패: {type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
        return 1
    for k, v in out.items():
        print(f"{k}: {v}")
    return 0


def cmd_schedule(a) -> int:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("pip install apscheduler")
        return 2
    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    ch, cm = (settings.collect_at or "02:00").split(":")
    nh, nm = (settings.notify_at or "08:00").split(":")
    sched = BlockingScheduler(timezone="Asia/Seoul")

    def job_collect():
        cc = user_client()
        if repo.acquire_lock(cc, date.today(), "batch", pc_name()):
            print(date.today(), "수집 배치 시작")
            stages = ("collect", "lookup", "score") + (("monitor",) if monitor_due(cc) else ())
            print(run_stages(user_client(), uid, stages))

    def job_notify():
        if repo.acquire_lock(user_client(), date.today(), "notify", pc_name()):
            print(date.today(), "알림 시작")
            print(run_stages(user_client(), uid, ("notify",)))

    sched.add_job(job_collect, CronTrigger(hour=int(ch), minute=int(cm)), id="collect")
    sched.add_job(job_notify, CronTrigger(hour=int(nh), minute=int(nm)), id="notify")
    print(f"스케줄 등록: 수집 {settings.collect_at} · 알림 {settings.notify_at} (Asia/Seoul) · PC {pc_name()} · Ctrl+C 종료")
    try:
        sched.start()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_status(a) -> int:
    c = user_client()
    uid = current_user_id(c)
    today = date.today().isoformat()
    locks = c.table("batch_locks").select("kind, pc_name, acquired_at, heartbeat_at").eq("run_date", today).execute().data
    cands = c.table("candidates").select("status", count="exact").eq("run_date", today).execute()
    by = {}
    for r in c.table("candidates").select("status").eq("run_date", today).execute().data:
        by[r["status"]] = by.get(r["status"], 0) + 1
    logs = c.table("run_logs").select("kind, started_at, finished_at, counts_json, error, pc_name").order("started_at", desc=True).limit(5).execute().data
    print(f"오늘 {today} · 잠금 {locks or '없음'}")
    print(f"후보 {cands.count or 0}건: {by}")
    for lg in logs:
        print(f"  {lg['kind']:<8} {lg['started_at'][:19]} {lg.get('pc_name') or ''} {lg['counts_json']} {('! ' + lg['error']) if lg.get('error') else ''}")
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stage", choices=STAGES)
    r.add_argument("--headed", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-lock", action="store_true")
    sub.add_parser("schedule")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    return {"run": cmd_run, "schedule": cmd_schedule, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
