"""1688 내장 어댑터 (목록 · 상세). 로그인 프로필(persistent context) 필수 — 헤드리스는 로그인으로 튕긴다.

  python -m app.sources.s1688 --profile 1688 --headed <목록URL>            # 1회: 창 띄워 로그인 후 그대로 수집
  python -m app.sources.s1688 --profile 1688 --pages 2 <목록URL> -o samples.json   # 규칙 생성기 샘플 만들기
  python -m app.sources.s1688 --profile 1688 --detail <상세URL>

파싱 전략: 클래스명이 자주 바뀌므로 셀렉터 대신 "detail.1688.com/offer/<id>.html 로 가는 링크를 가진 카드" 를
찾아 가격(¥) · 起批 · 이미지 · 제목을 텍스트 패턴으로 읽는다(naver_crawl 과 같은 방식). 셀렉터가 필요해지면
rulesets(kind=extract) 가 덮어쓴다. 1688 은 무한 스크롤형 목록이 많아 페이지 안에서 스크롤로 카드를 더 모은다.
"""
from __future__ import annotations

import random
import re
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from app.sources.base import Blocked, RawDetail, RawListing, SourceAdapter

OFFER_RE = re.compile(r"detail\.1688\.com/offer/(\d+)\.html")
BLOCK_MARKERS = ("login.1688.com", "滑动验证", "请完成安全验证", "captcha", "访问受限", "login.taobao.com", "passport.alibaba.com")

JS_CARDS = r"""() => {
  const out=[]; const seen=new Set();
  const priceRe=/[¥￥]\s*\d/;
  for (const a of document.querySelectorAll('a[href*="detail.1688.com/offer/"]')) {
    const h=a.href||''; const m=h.match(/offer\/(\d+)\.html/); if(!m) continue;
    let card=a;
    for(let i=0;i<7&&card.parentElement;i++){ card=card.parentElement; const t=card.innerText||''; if(priceRe.test(t)&&card.querySelector('img')) break; }
    if(!card||card.tagName==='BODY') continue;
    const t=(card.innerText||'').replace(/\s+/g,' ').trim();
    if(!priceRe.test(t)||t.length>800) continue;
    if(seen.has(m[1])) continue; seen.add(m[1]);
    const img=card.querySelector('img');
    let src=img?(img.currentSrc||img.src||img.getAttribute('data-src')||''):'';
    const titleEl=card.querySelector('[title]');
    const title=(titleEl&&titleEl.getAttribute('title'))||(img&&img.alt)||'';
    out.push({id:m[1], href:'https://detail.1688.com/offer/'+m[1]+'.html', text:t, img:src, title:title.trim()});
  }
  return out;
}"""

JS_DETAIL = r"""() => {
  const attrs={};
  // 속성표: dt/dd · th/td · "키 값" 2열 테이블 · span 쌍
  for (const row of document.querySelectorAll('tr, dl, li')) {
    const cells=[...row.querySelectorAll('th,td,dt,dd,span')].map(e=>(e.innerText||'').trim()).filter(Boolean);
    for(let i=0;i+1<cells.length;i+=2){ const k=cells[i].replace(/[:：]$/,''); if(k.length<=12&&cells[i+1].length<=80&&!(k in attrs)) attrs[k]=cells[i+1]; }
  }
  const imgs=[]; const seen=new Set();
  for (const img of document.images){ const s=img.currentSrc||img.src||''; if(!s||s.startsWith('data:')) continue; if((img.naturalWidth||0)<200) continue; if(seen.has(s)) continue; seen.add(s); imgs.push(s); }
  const metas={}; for(const m of document.querySelectorAll('meta[property],meta[name]')){ const k=m.getAttribute('property')||m.getAttribute('name'); const v=m.getAttribute('content'); if(k&&v&&(k.startsWith('og:')||k==='description')) metas[k]=v; }
  const crumbs=[...document.querySelectorAll('[class*="crumb"] a, [class*="breadcrumb"] a, [class*="Crumb"] a')].map(a=>(a.innerText||'').trim()).filter(Boolean);
  return {title:document.title, text:(document.body.innerText||'').slice(0,20000), attrs, imgs, metas, crumbs, url:location.href};
}"""


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_price(text: str) -> tuple[str, list[dict]]:
    """'¥12.50-15.00' · '¥ 12.5 起' · '¥12.5 2件起批' 등에서 (원문, tiers). 구간은 최저가를 1구간 단가로."""
    m = re.search(r"[¥￥]\s*([\d,]+(?:\.\d+)?)(?:\s*[-~～]\s*[¥￥]?\s*([\d,]+(?:\.\d+)?))?", text)
    if not m:
        return "", []
    raw = m.group(0).strip()
    low = _num(m.group(1))
    tiers = [{"min_qty": 1, "unit_price": low}]
    # "≥2件 ¥12.5 ≥10件 ¥11.8" 식 다단가
    multi = re.findall(r"[≥>]\s*(\d+)\s*[件个套双条盒包]\s*[¥￥]\s*([\d,]+(?:\.\d+)?)", text)
    if multi:
        tiers = [{"min_qty": int(q), "unit_price": _num(p)} for q, p in multi]
    return raw, tiers


def parse_moq(text: str) -> int:
    m = re.search(r"(\d+)\s*[件个套双条盒包张只]\s*起批", text) or re.search(r"起批量?\s*[:：]?\s*(\d+)", text) or re.search(r"≥\s*(\d+)\s*[件个套]", text)
    return int(m.group(1)) if m else 1


def parse_sales(text: str) -> int | None:
    m = re.search(r"(?:成交|已售|销量)\s*([\d.]+)\s*(万)?", text)
    if not m:
        return None
    v = float(m.group(1)) * (10000 if m.group(2) else 1)
    return int(v)


def card_to_listing(c: dict) -> RawListing | None:
    t = c.get("text", "")
    price_raw, tiers = parse_price(t)
    if not price_raw:
        return None
    title = c.get("title") or t.split(" ¥")[0].split(" ￥")[0][:120]
    img = c.get("img", "")
    img = re.sub(r"_\.(avif|webp)$", "", img)
    img = re.sub(r"\.(jpg|png)_\d+x\d+(?:q\d+)?\.(?:jpg|png)$", r".\1", img)   # 썸네일 접미사 제거 → 원본
    ext = {}
    sales = parse_sales(t)
    if sales is not None:
        ext["sales"] = sales
    m = re.search(r"回头率\s*([\d.]+)%", t)
    if m:
        ext["repeat_rate"] = float(m.group(1))
    return RawListing(
        source_id="1688", item_id=c["id"], url=c["href"], title_raw=title, lang="zh",
        price_raw=price_raw, price_tiers=tiers, currency="CNY", moq=parse_moq(t), image_url=img, extra=ext,
    )


def page_url(list_url: str, page: int) -> str:
    """beginPage(검색) · pageNum · page 파라미터를 알아서 붙인다."""
    if page <= 1:
        return list_url
    u = urllib.parse.urlsplit(list_url)
    q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
    key = next((k for k in ("beginPage", "pageNum", "page", "pageNo") if k in q), None) or ("beginPage" if "s.1688.com" in u.netloc else "page")
    q[key] = str(page)
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))


class Adapter1688(SourceAdapter):
    key = "1688"

    def open(self) -> None:
        if not self.profile_dir:
            raise RuntimeError("1688 은 로그인 프로필이 필요합니다: --profile 1688 (data/profiles/1688)")
        from app import browser

        self._pw = sync_playwright().start()
        self.ctx = browser.launch_persistent(
            self._pw, self.profile_dir, headless=not self.headed, locale="zh-CN", viewport={"width": 1366, "height": 900},
        )
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        if self.headed:
            print(f"브라우저: {browser.working_channel()} · 프로필 {self.profile_dir}")

    def close(self) -> None:
        try:
            self.ctx.close()
        finally:
            self._pw.stop()

    def _goto(self, url: str, wait_ms: int = 2500) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except PWTimeout:
            pass
        self.page.wait_for_timeout(wait_ms)
        self._check_blocked()

    def _check_blocked(self) -> None:
        url = self.page.url
        body = ""
        try:
            body = (self.page.evaluate("document.body ? document.body.innerText.slice(0, 3000) : ''") or "")
        except Exception:
            pass
        probe = (url + " " + body).lower()
        if any(m.lower() in probe for m in BLOCK_MARKERS):
            if self.headed:
                # 창이 떠 있으면 사용자가 직접 로그인/인증할 시간을 준다
                print("로그인 또는 인증 페이지입니다. 창에서 처리하면 60초 안에 이어갑니다…")
                for _ in range(60):
                    time.sleep(1)
                    probe2 = (self.page.url + " " + (self.page.evaluate("document.body ? document.body.innerText.slice(0,3000) : ''") or "")).lower()
                    if not any(m.lower() in probe2 for m in BLOCK_MARKERS):
                        return
            raise Blocked(f"1688 차단/로그인 페이지: {url[:120]}")

    def list(self, list_url: str, page: int = 1) -> list[RawListing]:
        if page > 1:
            time.sleep(random.uniform(*self.delay_range))
        self._goto(page_url(list_url, page))
        # 무한 스크롤 · 지연 로딩: 몇 번 내려서 카드를 더 모은다
        for _ in range(6):
            self.page.mouse.wheel(0, 1600)
            self.page.wait_for_timeout(500)
        cards = self.page.evaluate(JS_CARDS)
        out: list[RawListing] = []
        for c in cards:
            li = card_to_listing(c)
            if li:
                out.append(li)
        return out

    def detail(self, item_url: str) -> RawDetail:
        time.sleep(random.uniform(*self.delay_range))
        self._goto(item_url, wait_ms=3000)
        for y in (800, 1800, 3000, 0):
            self.page.mouse.wheel(0, y)
            self.page.wait_for_timeout(300)
        data = self.page.evaluate(JS_DETAIL)
        text = data.get("text") or ""
        price_raw, tiers = parse_price(text)
        m = OFFER_RE.search(item_url)
        attrs = data.get("attrs") or {}
        weight = attrs.get("重量") or attrs.get("毛重") or attrs.get("净重") or ""
        return RawDetail(
            source_id="1688", item_id=m.group(1) if m else item_url, url=item_url,
            title_raw=(data.get("metas") or {}).get("og:title") or (data.get("title") or "").split(" - ")[0], lang="zh",
            price_raw=price_raw, price_tiers=tiers, currency="CNY", moq=parse_moq(text),
            image_url=(data.get("metas") or {}).get("og:image") or (data["imgs"][0] if data.get("imgs") else ""),
            category_raw=" > ".join(data.get("crumbs") or []), attrs_raw=attrs, weight_raw=weight,
            sold_out=("已下架" in text or "商品不存在" in text),
            images=list(data.get("imgs") or [])[:30], attrs_full=attrs, package_weight_raw=weight,
            extra={"sales": parse_sales(text)} if parse_sales(text) is not None else {},
        )


def main(argv=None) -> int:
    import argparse
    import json
    import sys

    from app.config import settings

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="1688 어댑터 테스트")
    ap.add_argument("url")
    ap.add_argument("--profile", default="1688")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--detail", action="store_true", help="상세 1건")
    ap.add_argument("-o", "--out", help="JSON 저장 경로 (규칙 생성기 샘플)")
    a = ap.parse_args(argv)
    with Adapter1688(profile_dir=settings.profiles_dir / a.profile, headed=a.headed) as ad:
        if a.detail:
            rows = [ad.detail(a.url).to_dict()]
        else:
            rows = []
            for p, items in ad.iter_pages(a.url, a.pages):
                print(f"페이지 {p}: 카드 {len(items)}건")
                rows += [i.to_dict() for i in items]
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장 {a.out} ({len(rows)}건)")
    else:
        for r in rows[:5]:
            print(json.dumps({k: r[k] for k in ("item_id", "title_raw", "price_raw", "moq", "image_url")}, ensure_ascii=False))
        print(f"… 총 {len(rows)}건")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
