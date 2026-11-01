"""⑥ 상세 수집 · ⑦ 콘텐츠 생성 · ⑧ 2차 카드 (DESIGN.md 2장 · 6장). 승인된 상품만, 여기서 LLM 을 쓴다.

  python -m app.pipeline.content                 # approved_1 → ⑥⑦⑧, revise(메모 있음) → ⑦⑧ 재생성
  python -m app.pipeline.content --cand 17 [--no-telegram]

⑦ LLM 1회: 상품명 후보 3개(≤50자) · 설명 문단 · 불릿 · 옵션 한국어화. 같은 입력이면 ai_results 캐시(0회).
금지 문구(최상급 · 효능)는 LLM 에게도 피하라고 하고 로컬 규칙으로 한 번 더 걸러 forbidden_hits 에 남긴다.
고정 블록(구매대행 고지 · 배송 · 반품 · 통관)은 배송 프로필의 국가 · 배송일로 채운다. 이미지 모드 A = 소스 원본 그대로.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app import repo
from app.adapters.llm.base import ImageRef
from app.config import settings

FORBIDDEN = ["최고", "최상", "최고급", "1위", "완치", "치료", "효능", "효과 보장", "100%", "유일", "최초", "특효", "만병", "살균", "항균 99", "다이어트 효과", "의학적", "FDA"]
COUNTRY_KO = {"CN": "중국", "JP": "일본", "US": "미국"}


class OptionKo(BaseModel):
    name_raw: str
    name_ko: str = Field(description="한국 소비자용 옵션명 (색상 · 용량 표준 표기)")
    sell: bool = Field(default=True, description="판매할 옵션인가 (품절 · 비정상 옵션은 false)")


class ContentOut(BaseModel):
    title_options: list[str] = Field(description="상품명 후보 3개, 각 50자 이내, 브랜드명 제외, 핵심 키워드(종류 · 용량 · 재질 · 특징) 조합, 광고어 · 최상급 금지")
    bullet_points: list[str] = Field(description="핵심 특징 4~6개, 각 40자 이내, 사실만")
    description_paragraphs: list[str] = Field(description="상세 설명 3~5 문단, 한국어, 효능 · 최상급 · 의학적 표현 금지, 실제 속성만")
    options_ko: list[OptionKo]
    notes: str = Field(description="판매자가 알아야 할 점 (요건 · 주의 · 누락 정보)")


SYSTEM = (
    "너는 한국 네이버 스마트스토어 구매대행 셀러의 상품 등록 작가다. 해외 도매 상품 원문(중국어 등)을 한국 소비자용 등록 콘텐츠로 만든다. "
    "규칙: 사실만 쓴다(원문 · 속성표에 없는 기능을 지어내지 않는다). 브랜드명 · 캐릭터명은 쓰지 않는다. 최상급(최고 · 1위 · 유일) · 효능 · 의학적 표현 · '100%' 를 쓰지 않는다. "
    "상품명은 네이버 검색 키워드가 앞에 오게 하고 50자 이내. 옵션명은 한국어 표준(색상 · 용량 · 사이즈)으로."
)


def forbidden_hits(*texts: str) -> list[str]:
    joined = " ".join(t for t in texts if t)
    return sorted({w for w in FORBIDDEN if w in joined})


def blocks_for(country: str, lead_days: int, template: str | None = None) -> dict:
    ko = COUNTRY_KO.get(country, country)
    notice = (template or "본 상품은 {country}에서 발송되는 해외 구매대행 상품입니다. 통관을 위해 개인통관고유부호가 필요하며, 배송 기간은 영업일 기준 {lead_days}일 내외입니다. "
              "해외 현지 사정에 따라 지연될 수 있습니다.").format(country=ko, lead_days=lead_days)
    return {
        "notice": notice,
        "shipping": f"{ko} 현지 출고 → 배송대행지 → 국내 통관 → 택배. 주문 후 {lead_days}일 내외 도착 (주말 · 공휴일 · 현지 명절 제외).",
        "returns": "해외 구매대행 특성상 단순 변심 반품 시 해외 반송 비용이 발생하며, 상품 수령 후 7일 이내 미개봉 상태에서만 가능합니다. 불량 · 오배송은 전액 처리합니다.",
        "customs": "목록통관 대상(미화 150달러 이하)으로 관부가세가 별도 부과되지 않으나, 합산 과세 시 구매자 부담이 발생할 수 있습니다. 개인통관고유부호를 정확히 입력해 주세요.",
    }


def description_html(out: ContentOut, blocks: dict) -> str:
    parts = ["<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in out.bullet_points) + "</ul>"]
    parts += [f"<p>{_esc(p)}</p>" for p in out.description_paragraphs]
    parts.append("<hr>")
    for k, label in (("notice", "구매대행 안내"), ("shipping", "배송"), ("returns", "교환 · 반품"), ("customs", "통관")):
        parts.append(f"<h4>{label}</h4><p>{_esc(blocks[k])}</p>")
    return "\n".join(parts)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _budget_ok(c) -> tuple[bool, float]:
    try:
        used = float(c.rpc("my_month_api_cost").execute().data or 0)
    except Exception:
        used = 0.0
    us = (c.table("user_settings").select("monthly_budget_krw, budget_exceeded_action").limit(1).execute().data or [{}])[0]
    budget = float(us.get("monthly_budget_krw") or 0)
    if budget and used >= budget and (us.get("budget_exceeded_action") or "stop_content") == "stop_content":
        return False, used
    return True, used


# ───────────────────────── ⑥ 상세 수집 ─────────────────────────
def collect_detail(c, cand: dict, *, headed: bool = False) -> dict:
    from app.pipeline.collector import make_adapter

    item = c.table("source_items").select("*").eq("id", cand["source_item_id"]).limit(1).execute().data[0]
    have = c.table("source_item_details").select("*").eq("source_item_id", item["id"]).limit(1).execute().data
    if have and have[0].get("options_json") and have[0].get("fetched_at", "") >= (datetime.now(timezone.utc).isoformat()[:10]):
        detail = have[0]   # 오늘 이미 수집함 (즉시 분석 등)
    else:
        src = c.table("sources").select("*").eq("id", item["source_id"]).limit(1).execute().data[0]
        us = repo.my_user_sources(c).get(item["source_id"]) or {}
        with make_adapter(src["adapter_key"], us, headed=headed) as ad:
            d = ad.detail(item["url"])
        from app.instant import _store_detail

        _store_detail(c, d)
        if d.title_raw and d.title_raw != item.get("title_raw"):
            c.table("source_items").update({"title_raw": d.title_raw}).eq("id", item["id"]).execute()
        detail = c.table("source_item_details").select("*").eq("source_item_id", item["id"]).limit(1).execute().data[0]
    c.table("candidates").update({"status": "detail_collected"}).eq("id", cand["id"]).execute()
    return detail


# ───────────────────────── ⑦ 콘텐츠 생성 ─────────────────────────
def generate(c, uid: str, cand: dict, llm, *, revise_note: str = "") -> dict:
    ok, used = _budget_ok(c)
    if not ok:
        raise RuntimeError(f"월 API 예산 초과 ({used:,.0f}원) → ⑦ 중단 (설정 budget_exceeded_action)")
    item = c.table("source_items").select("*").eq("id", cand["source_item_id"]).limit(1).execute().data[0]
    norm = (c.table("source_items_normalized").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    detail = (c.table("source_item_details").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    sig = (c.table("market_signals").select("*").eq("source_item_id", item["id"]).limit(1).execute().data or [{}])[0]
    cat = None
    if norm.get("canonical_category_id"):
        cat = (c.table("canonical_categories").select("path, item_type").eq("id", norm["canonical_category_id"]).limit(1).execute().data or [None])[0]
    # 배송 프로필 → 고지 블록
    us = repo.my_user_sources(c).get(item["source_id"]) or {}
    sp = (c.table("shipping_profiles").select("country, lead_days").eq("id", us.get("shipping_profile_id")).limit(1).execute().data or [{}])[0] if us.get("shipping_profile_id") else {}
    tmpl = (c.table("user_settings").select("notice_template").limit(1).execute().data or [{}])[0].get("notice_template")
    blocks = blocks_for(sp.get("country") or "CN", int(sp.get("lead_days") or 12), tmpl)
    # 네이버 정확/유사 상품 제목 = 한국어 키워드 힌트
    mrows = c.table("matches").select("nv_mid, relation").eq("source_item_id", item["id"]).in_("relation", ["exact", "similar"]).limit(10).execute().data
    titles_ko = []
    if mrows:
        nv = c.table("naver_items").select("title").in_("nv_mid", [m["nv_mid"] for m in mrows]).limit(10).execute().data
        titles_ko = [x["title"] for x in nv][:8]
    options = [o.get("name_raw") or o.get("name") for o in (detail.get("options_json") or []) if (o.get("name_raw") or o.get("name"))][:30]
    attrs = detail.get("attrs_full_json") or item.get("attrs_raw_json") or {}
    prompt = (
        f"원문 상품명: {item['title_raw']}\n정규화 제목: {norm.get('title_clean')}\n표준 카테고리: {cat['path'] if cat else '-'} · 품목 {norm.get('item_type')}\n"
        f"재질 코드: {norm.get('material_code')} · 핵심 숫자: {norm.get('key_numbers_json')}\n속성표: {dict(list(attrs.items())[:25])}\n"
        f"옵션(원문): {options}\n네이버 검색어: {norm.get('search_queries')}\n국내 유사 상품 제목(키워드 참고, 베끼지 말 것): {titles_ko}\n"
        f"무게: {detail.get('package_weight_g')}g\n" + (f"\n[수정 요청] {revise_note}\n" if revise_note else "")
    )
    images = [ImageRef(item.get("main_image_url"), "대표 이미지")] if item.get("main_image_url") else []
    out: ContentOut = llm.complete_json(prompt, ContentOut, system=SYSTEM, images=images, purpose="content_generate", effort="medium")
    hits = forbidden_hits(*out.title_options, *out.bullet_points, *out.description_paragraphs)
    titles = [t.strip()[:50] for t in out.title_options if t.strip()][:3]
    html = description_html(out, blocks)
    imgs = [u for u in (detail.get("images") or []) if u][:12] or ([item["main_image_url"]] if item.get("main_image_url") else [])
    # 옵션 한국어 + 소스 옵션가 결합
    price_by_raw = {(o.get("name_raw") or o.get("name")): o.get("price") for o in (detail.get("options_json") or [])}
    opts = [{"name_raw": o.name_raw, "name_ko": o.name_ko, "sell": o.sell, "price_src": price_by_raw.get(o.name_raw)} for o in out.options_ko]
    cost = llm.total_cost_krw()
    row = {"candidate_id": cand["id"], "user_id": uid, "title_options": titles, "title_chosen": titles[0] if titles else None, "description_html": html,
           "options_ko_json": opts, "blocks_json": blocks, "image_urls": imgs, "mode": "A", "forbidden_hits": hits, "revise_note": revise_note or None, "llm_cost_krw": cost}
    c.table("generated_contents").upsert(row, on_conflict="candidate_id").execute()
    # 공용 초안 캐시 (상품명 · 옵션은 사실에 가까움 → 다른 계정도 재사용)
    try:
        c.table("source_item_ko_drafts").upsert({"source_item_id": item["id"], "title_ko_options": titles, "options_ko_json": opts}, on_conflict="source_item_id").execute()
    except Exception:
        pass
    c.table("candidates").update({"status": "content_generated"}).eq("id", cand["id"]).execute()
    for u in llm.usage:
        try:
            c.table("api_usage").insert({"user_id": uid, "provider": u.provider, "model": u.model, "purpose": u.purpose, "candidate_id": cand["id"], "input_tokens": u.input_tokens,
                                         "output_tokens": u.output_tokens, "est_cost_krw": u.est_cost_krw, "cache_hit": u.cache_hit}).execute()
        except Exception:
            pass
    row["notes"] = out.notes
    return row


# ───────────────────────── ⑧ 2차 카드 ─────────────────────────
def card2_text(cand: dict, content: dict, item: dict) -> str:
    opts = content.get("options_ko_json") or []
    sell = [o["name_ko"] for o in opts if o.get("sell", True)][:8]
    lines = [
        f"[2차] {content.get('title_chosen') or ''}",
        f"판매가 제안  {int(cand.get('suggested_price_krw') or 0):,}원  (마진율 {((cand.get('margin_rate') or 0) * 100):.0f}% 기준 총원가 {int((cand.get('cost_breakdown_json') or {}).get('total_cost_krw') or 0):,}원)",
        f"상품명 후보  " + " | ".join(content.get("title_options") or []),
        f"옵션 {len(opts)}개 (판매 {len(sell)})  " + ", ".join(sell) + (" …" if len(opts) > 8 else ""),
        f"이미지 {len(content.get('image_urls') or [])}장 · 모드 {content.get('mode')}",
    ]
    if content.get("forbidden_hits"):
        lines.append("금지 문구 감지  " + ", ".join(content["forbidden_hits"]) + " → 수정 요청 권장")
    if content.get("notes"):
        lines.append(f"메모  {content['notes'][:200]}")
    lines.append(f"링크  {item.get('url', '')}")
    return "\n".join(lines)


def send_card2(c, cand: dict, content: dict, bot) -> None:
    from app.adapters.telegram import callback_data

    item = c.table("source_items").select("url, main_image_url").eq("id", cand["source_item_id"]).limit(1).execute().data[0]
    text = card2_text(cand, content, item)
    buttons = [[("등록 패키지 생성", callback_data("p", cand["id"], "package")), ("수정 요청", callback_data("p", cand["id"], "revise")), ("폐기", callback_data("p", cand["id"], "discard"))]]
    img = (content.get("image_urls") or [None])[0] or item.get("main_image_url") or ""
    bot.send_photo(img, text, buttons=buttons) if img else bot.send_text(text, buttons=buttons)


# ───────────────────────── 실행 ─────────────────────────
def process_one(c, uid: str, cand: dict, llm, bot=None, *, revise_note: str = "", headed: bool = False) -> dict:
    if cand["status"] in ("approved_1",):
        collect_detail(c, cand, headed=headed)
    content = generate(c, uid, cand, llm, revise_note=revise_note)
    if bot is not None:
        send_card2(c, cand, content, bot)
    return content


def run(c, uid: str, *, only: int | None = None, bot=None, headed: bool = False) -> dict:
    from app.adapters.llm import get_llm
    from app.ai_cache import SupabaseCache, set_backend

    set_backend(SupabaseCache(c))
    q = c.table("candidates").select("*").in_("status", ["approved_1", "revise"])
    if only:
        q = c.table("candidates").select("*").eq("id", only)
    cands = q.execute().data
    out = {"done": 0, "errors": []}
    for cand in cands:
        try:
            llm = get_llm()
            note = ""
            if cand["status"] == "revise":
                gc = c.table("generated_contents").select("revise_note").eq("candidate_id", cand["id"]).limit(1).execute().data
                note = (gc[0].get("revise_note") if gc else "") or ""
            process_one(c, uid, cand, llm, bot, revise_note=note, headed=headed)
            out["done"] += 1
        except Exception as e:
            out["errors"].append(f"#{cand['id']}: {type(e).__name__}: {e}")
    return out


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", type=int)
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args(argv)
    from app.db import current_user_id, user_client
    from app.user_settings import ensure_user_settings

    c = user_client()
    uid = current_user_id(c)
    ensure_user_settings(c, uid)
    bot = None
    if not a.no_telegram:
        try:
            from app.adapters.telegram import bot_from

            bot = bot_from(c)
        except Exception as e:
            print("텔레그램 없음:", e)
    r = run(c, uid, only=a.cand, bot=bot, headed=a.headed)
    print(r)
    if a.cand:
        gc = c.table("generated_contents").select("title_options, options_ko_json, forbidden_hits, llm_cost_krw, image_urls").eq("candidate_id", a.cand).limit(1).execute().data
        if gc:
            g = gc[0]
            print("상품명 후보:", g["title_options"]); print("옵션:", [(o["name_raw"], o["name_ko"], o["sell"]) for o in g["options_ko_json"]][:6]); print("금지어:", g["forbidden_hits"], "· 이미지", len(g["image_urls"]), "· LLM", g["llm_cost_krw"], "원")
    return 0 if not r["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
