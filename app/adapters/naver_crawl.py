"""네이버 쇼핑 가격 수집기 (크롤링).

쇼핑 검색 API 가 2026-07-31 종료되어 네이버 통합검색 페이지의 쇼핑 블록을 Playwright 로 읽는다.
- 로그인 없이 열리고, 카드마다 제목·최저가·배송비·평점(리뷰 수)·찜·판매처 수·이미지·nv_mid·카테고리 id 가 들어 있다.
- 클래스명이 해시라 자주 바뀌므로 셀렉터 대신 "쇼핑 링크를 가진 카드의 텍스트 패턴"으로 파싱한다.
- 후보 상품에 한해 소량만 호출한다. 요청 사이 지연과 차단 감지를 둔다.
"""
from __future__ import annotations

import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

SEARCH_URL = "https://search.naver.com/search.naver?where=nexearch&query={q}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

JS_CARDS = r"""() => {
  const out=[]; const seen=new Set();
  const priceRe=/\d{1,3}(,\d{3})+\s*원/;
  for (const a of document.querySelectorAll('a[href]')) {
    const h=a.href||'';
    if (!/(cr\d*\.shopping\.naver\.com|search\.shopping\.naver\.com|smartstore\.naver\.com|brand\.naver\.com|shopping\.naver\.com\/(catalog|window-products))/.test(h)) continue;
    // 광고 블록(UL 전체)이 잡히지 않도록 LI/DIV 단위 카드만 취한다
    let card=a;
    for(let i=0;i<6&&card.parentElement;i++){
      card=card.parentElement;
      const t=card.innerText||'';
      if(priceRe.test(t)&&card.querySelector('img')) break;
    }
    if(card.tagName==='UL'||card.tagName==='BODY') continue;
    const t=(card.innerText||'').replace(/\s+/g,' ').trim();
    if(!priceRe.test(t)||t.length>600) continue;
    const img=card.querySelector('img');
    const title=(img&&img.alt?img.alt:'').replace(/<\/?mark>/g,'').trim();
    const key=(title||t.slice(0,60))+'|'+h.slice(0,80); if(seen.has(key)) continue; seen.add(key);
    const isAd=/\b광고\b/.test(t)||/nad-|adcr\./.test(h);
    out.push({text:t, href:h, img:img?img.src:'', title, isAd});
  }
  return out;
}"""

BLOCK_MARKERS = ("보안 확인", "자동 입력 방지", "captcha", "비정상적인 접근", "nidlogin")


@dataclass
class CrawledItem:
    title: str
    price: int
    shipping_krw: int | None
    rating: float | None
    review_count: int | None
    wish_count: int | None
    seller_count: int | None  # 가격비교 카탈로그의 판매처 수
    mall: str
    link: str
    image: str
    nv_mid: str
    cat_id: str
    kind: str  # catalog | store
    is_ad: bool


@dataclass
class CrawlResult:
    query: str
    items: list[CrawledItem] = field(default_factory=list)
    blocked: bool = False
    note: str = ""

    def to_dict(self):
        return {"query": self.query, "blocked": self.blocked, "note": self.note, "items": [asdict(i) for i in self.items]}


_num = lambda s: int(s.replace(",", ""))


def _parse_card(c: dict) -> CrawledItem | None:
    t = c["text"]
    href = c["href"]
    # 가격: "최저 29,450 원" > "할인 9,300 원" > 첫 번째 "N원"
    m = re.search(r"최저\s*([\d,]+)\s*원", t) or re.search(r"할인\s*([\d,]+)\s*원", t)
    if not m:
        prices = re.findall(r"([\d,]{4,})\s*원", t)
        prices = [p for p in prices if _num(p) >= 100]
        if not prices:
            return None
        price = _num(prices[-1]) if "판매가" in t and len(prices) > 1 else _num(prices[0])
    else:
        price = _num(m.group(1))
    ship = None
    ms = re.search(r"배송비\s*([\d,]+)\s*원", t)
    if ms:
        ship = _num(ms.group(1))
    elif "배송비 무료" in t or "무료배송" in t:
        ship = 0
    rating = review = None
    mr = re.search(r"(\d\.\d{1,2})\s*\(([\d,]+)\)", t)
    if mr:
        rating, review = float(mr.group(1)), _num(mr.group(2))
    else:
        mr2 = re.search(r"리뷰\s*([\d,]+)", t)
        if mr2:
            review = _num(mr2.group(1))
    wish = None
    mw = re.search(r"찜\s*([\d,]+)", t)
    if mw:
        wish = _num(mw.group(1))
    sellers = None
    msel = re.search(r"판매처\s*([\d,]+)", t)
    if msel:
        sellers = _num(msel.group(1))
    nv_mid = (re.search(r"nv_mid=(\d+)", href) or re.search(r"/catalog/(\d+)", href) or re.search(r"/products/(\d+)", href))
    cat = re.search(r"cat_id=(\d+)", href)
    kind = "catalog" if sellers is not None or "nv_mid=" in href or "/catalog/" in href else "store"
    # 판매자명: 스토어 카드는 평점 뒤에 상호가 온다
    mall = ""
    mm = re.search(r"\(\s*[\d,]+\s*\)\s*(.+?)(?:\s*공식)?$", t)
    if kind == "store" and mm:
        mall = mm.group(1).strip()[:30]
    elif kind == "catalog":
        mall = f"가격비교 {sellers}곳" if sellers else "가격비교"
    title = c["title"] or t.split(" 최저 ")[0].split(" 할인 전")[0][:80]
    return CrawledItem(
        title=title,
        price=price,
        shipping_krw=ship,
        rating=rating,
        review_count=review,
        wish_count=wish,
        seller_count=sellers,
        mall=mall,
        link=href,
        image=c["img"],
        nv_mid=nv_mid.group(1) if nv_mid else "",
        cat_id=cat.group(1) if cat else "",
        kind=kind,
        is_ad=bool(c.get("isAd")),
    )


def search(queries: list[str], *, profile_dir: Path | None = None, headed: bool = False, delay_range=(1.5, 3.5)) -> list[CrawlResult]:
    """여러 검색어를 한 브라우저 세션으로 순차 조회한다."""
    from app import browser as br

    results: list[CrawlResult] = []
    with sync_playwright() as p:
        if profile_dir:
            ctx = br.launch_persistent(p, profile_dir, headless=not headed, locale="ko-KR", viewport={"width": 1366, "height": 900})
            browser = None
        else:
            browser = br.launch(p, headless=not headed)
            ctx = browser.new_context(locale="ko-KR", user_agent=UA, viewport={"width": 1366, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            for i, q in enumerate(queries):
                if i:
                    time.sleep(random.uniform(*delay_range))
                r = CrawlResult(query=q)
                try:
                    page.goto(SEARCH_URL.format(q=urllib.parse.quote(q)), wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    for y in (800, 1600, 0):
                        page.mouse.wheel(0, y)
                        page.wait_for_timeout(250)
                    body = page.evaluate("document.body.innerText") or ""
                    if any(m in page.url or m in body[:1500] for m in BLOCK_MARKERS):
                        r.blocked, r.note = True, "차단/인증 페이지"
                    else:
                        cards = page.evaluate(JS_CARDS)
                        for c in cards:
                            it = _parse_card(c)
                            if it:
                                r.items.append(it)
                        if not r.items:
                            r.note = "쇼핑 카드 없음 (검색어가 너무 구체적이거나 블록 미노출)"
                except Exception as e:  # 한 검색어 실패가 전체를 멈추지 않게
                    r.note = f"{type(e).__name__}: {e}"
                results.append(r)
        finally:
            ctx.close()
            if browser:
                browser.close()
    return results


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    qs = sys.argv[1:] or ["스테인리스 보온 텀블러 500ml"]
    for r in search(qs):
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=1)[:4000])
