"""관리자 웹 라우터 (DESIGN.md 7장). 로그인은 CLI 와 같은 세션 파일(~/.auto-store/session.<env>.json)을 쓴다.

127.0.0.1 전용 1인 콘솔이라 쿠키 세션을 따로 두지 않는다 — 이 PC 에 로그인된 계정이 곧 사용자다.
모든 DB 호출은 anon 키 + 그 계정의 JWT 라 RLS 가 그대로 적용된다 (admin 메뉴도 DB 쪽 is_admin() 이 최종 판정).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, repo
from app.config import ROOT, settings
from app.db import NotLoggedIn, current_user_id, pc_name, user_client

app = FastAPI(title="auto-store 관리자", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(ROOT / "templates" / "admin"))

MENU = [
    ("/", "대시보드"), ("/candidates", "후보 목록"), ("/watch", "관심 카테고리"), ("/sources", "내 소스"),
    ("/settings", "설정"), ("/dict", "사전 관리"), ("/logs", "실행 로그"), ("/instant", "즉시 분석"),
]
STAGES = ("collect", "lookup", "score", "notify")
JOBS: dict[str, dict] = {}          # stage → {proc, log, started}
_client_cache: dict = {"c": None, "uid": None, "at": 0.0, "profile": None}


# ───────────────────────── 공통 ─────────────────────────
def get_client():
    """세션 파일로 로그인된 클라이언트. 60초 캐시. 없으면 None."""
    now = time.time()
    if _client_cache["c"] is not None and now - _client_cache["at"] < 60:
        return _client_cache["c"], _client_cache["uid"], _client_cache["profile"]
    try:
        c = user_client()
        uid = current_user_id(c)
        prof = c.table("profiles").select("display_name, role, telegram_chat_id").eq("user_id", uid).limit(1).execute().data
        _client_cache.update(c=c, uid=uid, at=now, profile=(prof[0] if prof else {}))
        return c, uid, _client_cache["profile"]
    except (NotLoggedIn, Exception):
        _client_cache.update(c=None, uid=None, at=0.0, profile=None)
        return None, None, None


def page(request: Request, name: str, **ctx):
    sess = auth.load_session() or {}
    base = {"request": request, "menu": MENU, "path": request.url.path, "env": settings.app_env, "email": sess.get("email"),
            "role": (ctx.get("profile") or {}).get("role", ""), "today": date.today().isoformat(), "flash": request.query_params.get("m", "")}
    return templates.TemplateResponse(request, name, {**base, **ctx})


def need_login(request: Request):
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


def _won(v):
    return "-" if v is None else f"{int(v):,}원"


templates.env.filters["won"] = _won
templates.env.filters["pct"] = lambda v: "-" if v is None else f"{float(v) * 100:.0f}%"
templates.env.filters["ts"] = lambda v: (v or "")[:16].replace("T", " ")


# ───────────────────────── 로그인 ─────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return page(request, "login.html", error="", next=request.query_params.get("next", "/"))


@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    try:
        auth.login(email, password)
    except SystemExit as e:
        return page(request, "login.html", error=str(e), next=next)
    _client_cache.update(c=None, at=0.0)
    return RedirectResponse(next or "/", status_code=303)


@app.get("/logout")
def logout():
    auth.clear_session()
    _client_cache.update(c=None, at=0.0)
    return RedirectResponse("/login", status_code=303)


# ───────────────────────── 대시보드 · 배치 실행 ─────────────────────────
def _counts(c, uid):
    today = date.today().isoformat()
    by: dict[str, int] = {}
    for r in c.table("candidates").select("status").eq("run_date", today).execute().data:
        by[r["status"]] = by.get(r["status"], 0) + 1
    shared = {}
    for t in ("source_items", "source_items_normalized", "naver_items", "images", "matches", "market_signals"):
        shared[t] = c.table(t).select("*", count="exact").limit(1).execute().count or 0
    pending = c.table("mapping_queue").select("*", count="exact").eq("status", "pending").limit(1).execute().count or 0
    locks = c.table("batch_locks").select("kind, pc_name, heartbeat_at").eq("run_date", today).execute().data
    try:
        cost = float(c.rpc("my_month_api_cost").execute().data or 0)
    except Exception:
        cost = 0.0
    rates = c.rpc("latest_exchange_rates").execute().data
    return {"by": by, "shared": shared, "pending": pending, "locks": locks, "cost": cost, "rates": rates}


def _jobs_view():
    out = []
    for st, j in JOBS.items():
        running = j["proc"].poll() is None
        out.append({"stage": st, "running": running, "started": j["started"], "rc": j["proc"].returncode, "log": j["log"].name})
    return out


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    logs = c.table("run_logs").select("kind, started_at, finished_at, counts_json, error, pc_name").order("started_at", desc=True).limit(8).execute().data
    return page(request, "dashboard.html", profile=prof, counts=_counts(c, uid), logs=logs, jobs=_jobs_view(), pc=pc_name(), settings=settings)


@app.post("/run/{stage}")
def run_stage(stage: str, request: Request):
    if stage not in STAGES:
        return PlainTextResponse("unknown stage", status_code=400)
    j = JOBS.get(stage)
    if j and j["proc"].poll() is None:
        return RedirectResponse("/?m=이미 실행 중: " + stage, status_code=303)
    logdir = settings.data_dir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logf = logdir / f"{stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    fh = logf.open("w", encoding="utf-8")
    env = {**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "app.worker", "run", "--stage", stage, "--no-lock"], cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, env=env)
    JOBS[stage] = {"proc": proc, "log": logf, "started": datetime.now().strftime("%H:%M:%S"), "fh": fh}
    return RedirectResponse(f"/?m={stage} 시작 (로그 {logf.name})", status_code=303)


@app.get("/jobs/{stage}/log", response_class=PlainTextResponse)
def job_log(stage: str):
    j = JOBS.get(stage)
    if not j:
        return "(없음)"
    try:
        text = Path(j["log"]).read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""
    tail = "\n".join(text.splitlines()[-40:])
    state = "실행 중" if j["proc"].poll() is None else f"종료 (코드 {j['proc'].returncode})"
    return f"[{stage} · {state} · 시작 {j['started']}]\n{tail}"


# ───────────────────────── 후보 ─────────────────────────
@app.get("/candidates", response_class=HTMLResponse)
def candidates(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    status = request.query_params.get("status", "")
    day = request.query_params.get("date", "")
    q = c.table("candidates").select("*").order("run_date", desc=True).order("score", desc=True).limit(200)
    if status:
        q = q.eq("status", status)
    if day:
        q = q.eq("run_date", day)
    rows = q.execute().data
    ids = [r["source_item_id"] for r in rows]
    items = {i["id"]: i for i in c.table("source_items").select("id, title_raw, url, main_image_url, source_id").in_("id", ids).execute().data} if ids else {}
    norms = {n["source_item_id"]: n for n in c.table("source_items_normalized").select("source_item_id, title_clean, search_queries").in_("source_item_id", ids).execute().data} if ids else {}
    statuses = ["candidate", "below_margin", "held", "rejected_1", "approved_1", "detail_collected", "content_generated", "approved_2", "packaged", "listed", "suspended"]
    return page(request, "candidates.html", profile=prof, rows=rows, items=items, norms=norms, status=status, day=day, statuses=statuses)


@app.get("/candidates/{cid}", response_class=HTMLResponse)
def candidate_detail(cid: int, request: Request):
    from app.pipeline.notify import FLAG_KO, render_card

    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = c.table("candidates").select("*").eq("id", cid).limit(1).execute().data
    if not rows:
        return RedirectResponse("/candidates?m=없는 후보", status_code=303)
    cand = rows[0]
    item = c.table("source_items").select("*").eq("id", cand["source_item_id"]).limit(1).execute().data[0]
    norm = (c.table("source_items_normalized").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    sig = (c.table("market_signals").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    matches = c.table("matches").select("nv_mid, relation, method, similarity, reason").eq("source_item_id", item["id"]).execute().data
    nv = {x["nv_mid"]: x for x in c.table("naver_items").select("*").in_("nv_mid", [m["nv_mid"] for m in matches]).execute().data} if matches else {}
    merged = sorted([{**nv.get(m["nv_mid"], {}), **m} for m in matches if m["nv_mid"] in nv], key=lambda m: (m["relation"] != "exact", m["method"] != "llm", -(m.get("similarity") or 0)))
    logo = (c.table("images").select("logo_checked_at, logo_detected, logo_reason").eq("kind", "source").eq("ref_id", str(item["id"])).limit(1).execute().data or [None])[0]
    card = render_card(item, norm, sig, cand, matches=merged, logo=logo, source_name=item["source_id"])
    return page(request, "candidate.html", profile=prof, cand=cand, item=item, norm=norm, sig=sig, matches=merged, card=card, logo=logo, flag_ko=FLAG_KO)


@app.post("/candidates/{cid}/{action}")
def candidate_action(cid: int, action: str, request: Request):
    from app.telegram_poll import decide

    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    label = decide(c, uid, cid, action)
    back = request.headers.get("referer") or f"/candidates/{cid}"
    sep = "&" if "?" in back else "?"
    return RedirectResponse(f"{back.split('?m=')[0]}{sep}m=#{cid} {label}", status_code=303)


# ───────────────────────── 관심 카테고리 ─────────────────────────
@app.get("/watch", response_class=HTMLResponse)
def watch(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = repo.my_watch_categories(c)
    allrows = c.table("user_watch_categories").select("id, enabled, max_pages, extra_keywords_ko, source_category_id").execute().data
    en = {r["id"]: r for r in allrows}
    for r in rows:
        r["enabled"] = True
    disabled = [r for r in allrows if not r["enabled"]]
    cats = c.table("canonical_categories").select("id, path").order("path").execute().data
    sources = c.table("sources").select("id, name, adapter_key").execute().data
    return page(request, "watch.html", profile=prof, rows=rows, disabled=disabled, cats=cats, sources=sources, en=en)


@app.post("/watch/add")
def watch_add(request: Request, source_id: str = Form(...), url: str = Form(...), label_raw: str = Form(""), canonical_category_id: str = Form(...),
              max_pages: int = Form(2), extra_keywords: str = Form("")):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    try:
        sc = c.table("source_categories").upsert({"source_id": source_id, "label_raw": label_raw or url[:40], "url": url.strip(), "canonical_category_id": canonical_category_id},
                                                 on_conflict="source_id,url").execute().data[0]
    except Exception as e:
        return RedirectResponse(f"/watch?m=소스 카테고리 저장 실패(admin 필요): {type(e).__name__}", status_code=303)
    kws = [k.strip() for k in extra_keywords.replace("|", ",").split(",") if k.strip()]
    c.table("user_watch_categories").upsert({"user_id": uid, "source_category_id": sc["id"], "max_pages": max_pages, "enabled": True, "extra_keywords_ko": kws},
                                            on_conflict="user_id,source_category_id").execute()
    c.table("user_sources").upsert({"user_id": uid, "source_id": source_id, "browser_profile_name": source_id, "enabled": True}, on_conflict="user_id,source_id", ignore_duplicates=True).execute()
    return RedirectResponse("/watch?m=추가됨", status_code=303)


@app.post("/watch/{wid}/toggle")
def watch_toggle(wid: int, request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    cur = c.table("user_watch_categories").select("enabled").eq("id", wid).limit(1).execute().data
    if cur:
        c.table("user_watch_categories").update({"enabled": not cur[0]["enabled"]}).eq("id", wid).execute()
    return RedirectResponse("/watch", status_code=303)


@app.post("/watch/{wid}/delete")
def watch_delete(wid: int, request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    c.table("user_watch_categories").delete().eq("id", wid).execute()
    return RedirectResponse("/watch?m=삭제됨", status_code=303)


# ───────────────────────── 내 소스 ─────────────────────────
@app.get("/sources", response_class=HTMLResponse)
def sources(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    defs = c.table("sources").select("*").execute().data
    mine = repo.my_user_sources(c)
    profiles = c.table("shipping_profiles").select("id, name, currency").execute().data
    return page(request, "sources.html", profile=prof, defs=defs, mine=mine, profiles=profiles)


@app.post("/sources/{sid}")
def sources_save(sid: str, request: Request, enabled: str = Form("off"), browser_profile_name: str = Form(""), delay_min_s: float = Form(2), delay_max_s: float = Form(6),
                 daily_cap: int = Form(300), block_tolerance: int = Form(3), shipping_profile_id: str = Form("")):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    row = {"user_id": uid, "source_id": sid, "enabled": enabled == "on", "browser_profile_name": browser_profile_name or sid, "delay_min_s": delay_min_s,
           "delay_max_s": delay_max_s, "daily_cap": daily_cap, "block_tolerance": block_tolerance, "shipping_profile_id": int(shipping_profile_id) if shipping_profile_id else None}
    c.table("user_sources").upsert(row, on_conflict="user_id,source_id").execute()
    return RedirectResponse("/sources?m=저장됨", status_code=303)


# ───────────────────────── 설정 · 시크릿 ─────────────────────────
SETTING_FIELDS = {
    "비용": [("proxy_fee_rate", "대리구매 수수료율"), ("local_shipping_cny", "현지 배송비 기본 (CNY)"), ("customs_duty_rate", "관세율"), ("vat_rate", "부가세율"),
            ("customs_limit_usd", "목록통관 한도 USD"), ("customs_warn_usd", "경계 경고 USD"), ("naver_fee_rate", "네이버 수수료율"), ("payment_fee_rate", "결제 수수료율"),
            ("fx_buffer_rate", "환차손 완충"), ("target_margin_rate", "목표 마진율"), ("margin_threshold", "후보 마진 기준"), ("forwarder_rates", "배대지 요율 (kg:원,…)")],
    "매칭": [("price_basis", "국내가 방식 mean|median|min"), ("match_preset", "프리셋 strict|normal|wide"), ("exact_threshold", "정확 임계(CLIP)"), ("similar_threshold", "유사 임계"),
            ("same_image_seller_cap", "동일 사진 판매자 cap"), ("llm_rejudge_top_n", "LLM 재판정 N (0=끔)"), ("naver_top_n", "네이버 상위 N")],
    "건수": [("daily_candidate_n", "하루 카드 N"), ("daily_lookup_cap", "하루 네이버 조회 상한"), ("daily_llm_cap", "하루 LLM 상한"), ("instant_daily_limit", "즉시 분석 상한")],
    "스케줄": [("collect_at", "수집 시각"), ("notify_at", "알림 시각"), ("days", "요일"), ("monitor_interval_days", "감시 주기(일)"), ("monitor_price_threshold", "감시 가격 임계")],
    "예산 · AI": [("monthly_budget_krw", "월 예산 (원)"), ("budget_warn_ratio", "경고 비율"), ("budget_exceeded_action", "초과 시 stop_content|warn_only"),
                ("llm_provider", "LLM 제공자 openai|claude|gemini"), ("llm_model", "모델 (비우면 기본)"), ("image_provider", "이미지 생성 none|gemini|openai"), ("image_mode", "이미지 모드 A|B|C")],
}
SECRET_NAMES = ["openai_api_key", "anthropic_api_key", "google_ai_api_key", "telegram_bot_token", "eximbank_api_key"]


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    us = (c.table("user_settings").select("*").eq("user_id", uid).limit(1).execute().data or [{}])[0]
    secrets = {r["name"]: r["value"] for r in c.table("user_secrets").select("name, value").execute().data}
    masked = {n: (v[:4] + "…" + v[-3:] if len(v) > 10 else "설정됨") for n, v in secrets.items()}
    return page(request, "settings.html", profile=prof, us=us, fields=SETTING_FIELDS, secret_names=SECRET_NAMES, masked=masked, chat_id=(prof or {}).get("telegram_chat_id") or "")


@app.post("/settings")
async def settings_save(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    form = await request.form()
    allowed = {k for group in SETTING_FIELDS.values() for k, _ in group}
    upd = {}
    for k, v in form.items():
        if k not in allowed:
            continue
        v = str(v).strip()
        if v == "":
            continue
        try:
            upd[k] = int(v) if v.lstrip("-").isdigit() else float(v)
        except ValueError:
            upd[k] = v
    if upd:
        c.table("user_settings").update(upd).eq("user_id", uid).execute()
    return RedirectResponse("/settings?m=저장됨 — 다음 실행부터 적용", status_code=303)


@app.post("/secrets")
def secrets_save(request: Request, name: str = Form(...), value: str = Form(""), telegram_chat_id: str = Form("")):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    if name == "telegram_chat_id":
        c.table("profiles").update({"telegram_chat_id": telegram_chat_id.strip() or None}).eq("user_id", uid).execute()
        _client_cache.update(at=0.0)
        return RedirectResponse("/settings?m=chat_id 저장", status_code=303)
    if name not in SECRET_NAMES:
        return RedirectResponse("/settings?m=알 수 없는 항목", status_code=303)
    if value.strip():
        c.table("user_secrets").upsert({"user_id": uid, "name": name, "value": value.strip()}, on_conflict="user_id,name").execute()
        msg = f"{name} 저장"
    else:
        c.table("user_secrets").delete().eq("user_id", uid).eq("name", name).execute()
        msg = f"{name} 삭제 (.env 값으로 복귀)"
    return RedirectResponse(f"/settings?m={msg}", status_code=303)


# ───────────────────────── 사전 관리 (admin) ─────────────────────────
@app.get("/dict", response_class=HTMLResponse)
def dict_page(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    queue = c.table("mapping_queue").select("*").eq("status", "pending").order("created_at", desc=True).limit(100).execute().data
    rulesets = c.table("rulesets").select("id, source_id, canonical_category_id, kind, version, status, coverage_json, generated_by, created_at").order("created_at", desc=True).limit(50).execute().data
    cats = c.table("canonical_categories").select("id, path").order("path").execute().data
    dv = c.rpc("current_dict_version").execute().data
    codes = sorted({r["code"] for r in c.table("attribute_aliases").select("code").eq("kind", "material").execute().data})
    counts = {t: (c.table(t).select("*", count="exact").limit(1).execute().count or 0) for t in ("canonical_categories", "category_aliases", "attribute_aliases", "brand_blacklist", "title_stopwords")}
    return page(request, "dict.html", profile=prof, queue=queue, rulesets=rulesets, cats=cats, dv=dv, codes=codes, counts=counts)


@app.post("/dict/queue/{qid}/{action}")
def dict_queue_action(qid: int, action: str, request: Request, target: str = Form("")):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = c.table("mapping_queue").select("*").eq("id", qid).limit(1).execute().data
    if not rows:
        return RedirectResponse("/dict?m=없는 항목", status_code=303)
    q = rows[0]
    try:
        if action == "approve" and target:
            if q["kind"] == "category":
                c.table("category_aliases").upsert({"term": q["term"], "lang": q["lang"], "canonical_category_id": target, "origin": "manual", "confidence": 1.0}, on_conflict="term,lang").execute()
            else:
                c.table("attribute_aliases").upsert({"kind": q["kind"], "term": q["term"], "lang": q["lang"], "code": target, "origin": "manual"}, on_conflict="kind,term,lang").execute()
            c.table("mapping_queue").update({"status": "approved", "suggested_id_or_code": target, "decided_at": datetime.now(timezone.utc).isoformat()}).eq("id", qid).execute()
            c.rpc("bump_dict_version").execute()
            msg = f"승인 → {target} (dict_version +1)"
        elif action == "reject":
            c.table("mapping_queue").update({"status": "rejected", "decided_at": datetime.now(timezone.utc).isoformat()}).eq("id", qid).execute()
            msg = "거절"
        else:
            msg = "대상을 고르세요"
    except Exception as e:
        msg = f"실패(admin 필요?): {type(e).__name__}"
    return RedirectResponse(f"/dict?m={msg}", status_code=303)


@app.post("/dict/rulesets/{rid}/{action}")
def ruleset_action(rid: int, action: str, request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = c.table("rulesets").select("*").eq("id", rid).limit(1).execute().data
    if not rows:
        return RedirectResponse("/dict?m=없는 규칙 세트", status_code=303)
    r = rows[0]
    try:
        if action == "activate":
            q = c.table("rulesets").update({"status": "retired"}).eq("source_id", r["source_id"]).eq("kind", r["kind"]).eq("status", "active")
            q = q.eq("canonical_category_id", r["canonical_category_id"]) if r["canonical_category_id"] else q.is_("canonical_category_id", "null")
            q.execute()
            c.table("rulesets").update({"status": "active", "approved_by": uid}).eq("id", rid).execute()
            msg = "활성화"
        elif action == "retire":
            c.table("rulesets").update({"status": "retired"}).eq("id", rid).execute()
            msg = "은퇴"
        else:
            msg = "?"
    except Exception as e:
        msg = f"실패(admin 필요?): {type(e).__name__}"
    return RedirectResponse(f"/dict?m={msg}", status_code=303)


# ───────────────────────── 로그 · 즉시 분석 ─────────────────────────
@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = c.table("run_logs").select("*").order("started_at", desc=True).limit(60).execute().data
    return page(request, "logs.html", profile=prof, rows=rows)


@app.get("/instant", response_class=HTMLResponse)
def instant(request: Request):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    rows = c.table("analysis_requests").select("*").order("requested_at", desc=True).limit(50).execute().data
    for r in rows:
        if r.get("candidate_id"):
            r["candidate_link"] = f"/candidates/{r['candidate_id']}"
    j = JOBS.get("instant")
    return page(request, "instant.html", profile=prof, rows=rows, jobs_instant=bool(j and j["proc"].poll() is None))


@app.post("/instant")
def instant_add(request: Request, urls: str = Form(...)):
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    n = 0
    for u in [x.strip() for x in urls.splitlines() if x.strip().startswith("http")][:20]:
        c.table("analysis_requests").insert({"user_id": uid, "channel": "web", "url": u, "status": "queued"}).execute()
        n += 1
    return RedirectResponse(f"/instant?m={n}건 큐에 추가 — '지금 처리' 를 누르거나 텔레그램 폴러가 돌고 있으면 자동", status_code=303)


@app.post("/instant/process")
def instant_process(request: Request):
    """큐를 서브프로세스로 처리 (대시보드 배치 버튼과 같은 방식). 텔레그램 토큰이 있으면 카드도 보낸다."""
    c, uid, prof = get_client()
    if c is None:
        return need_login(request)
    j = JOBS.get("instant")
    if j and j["proc"].poll() is None:
        return RedirectResponse("/instant?m=이미 처리 중", status_code=303)
    logdir = settings.data_dir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logf = logdir / f"instant-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    fh = logf.open("w", encoding="utf-8")
    env = {**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "app.instant", "--queue", "--limit", "5", "--telegram"], cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, env=env)
    JOBS["instant"] = {"proc": proc, "log": logf, "started": datetime.now().strftime("%H:%M:%S"), "fh": fh}
    return RedirectResponse("/instant?m=처리 시작 (대시보드에서 로그 확인)", status_code=303)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return f"ok {settings.app_env}"
