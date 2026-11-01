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
    // 제목 후보를 전부 모아 파이썬에서 고른다 (1688 은 회사명에 title 속성이 붙어 있어 첫 [title] 을 집으면 회사명이 나온다)
    const cands=[];
    const push=(s)=>{ s=(s||'').replace(/\s+/g,' ').trim(); if(s&&s.length>=4&&!cands.includes(s)) cands.push(s); };
    push(a.getAttribute('title')); push(a.innerText);
    for (const el of card.querySelectorAll('a[href*="detail.1688.com/offer/"]')) { push(el.getAttribute('title')); push(el.innerText); }
    if(img){ push(img.alt); push(img.getAttribute('title')); }
    for (const el of card.querySelectorAll('[title]')) push(el.getAttribute('title'));
    for (const el of card.querySelectorAll('h1,h2,h3,h4,p,span,div')) { const s=(el.innerText||'').trim(); if(s.length>=8&&s.length<=120&&!s.includes('¥')&&el.children.length===0) push(s); }
    out.push({id:m[1], href:'https://detail.1688.com/offer/'+m[1]+'.html', text:t, img:src, titles:cands.slice(0,12)});
  }
  return out;
}"""

JS_DIAG = r"""() => ({url:location.href, title:document.title, offers:document.querySelectorAll('a[href*="detail.1688.com/offer/"]').length,
  imgs:document.images.length, text:(document.body?document.body.innerText:'').replace(/\s+/g,' ').slice(0,400)})"""

COMPANY_RE = re.compile(r"(公司|有限公司|厂|工厂|商行|商店|专营店|旗舰店|批发部|经营部|合作社|工作室|贸易|实业|店)$")
PRICE_RE = re.compile(r"[¥￥]\s*\d")
# 카드 안의 툴팁 · 판촉 · 태그 문구 (상품명이 아님)
NOISE_RE = re.compile(r"(点此|交流|语音视频|下单返拿样费|首单减|免运费|功能上新|商机组货|红包价|新人价|退货包运费|先采后付|包邮|榜第\d+名|成交|起批|回头率|已售|销量|\+件|^\d+~\d+个$)")


def is_company_name(s: str) -> bool:
    s = s.strip()
    return bool(COMPANY_RE.search(s)) and len(s) <= 40


def pick_title(cands: list[str], text: str = "") -> tuple[str, str]:
    """(상품명, 회사명).

    1688 검색 카드 텍스트는 '<상품명> <판촉문구> ｜ 商机组货：<태그> ¥ 5 .9 红包价 全网4.8万+件 … <회사명>' 꼴이고
    상품명은 공백 없는 첫 토큰이다. 그 토큰으로 시작하는 후보(상세 제목 등)가 있으면 그것을, 없으면 토큰 자체를 쓴다.
    """
    company = next((c for c in cands if is_company_name(c)), "")
    clean = " ".join((text or "").split())
    first = clean.split(" ")[0] if clean else ""
    if len(first) >= 8 and not is_company_name(first) and not PRICE_RE.search(first) and not NOISE_RE.search(first):
        longer = [c for c in cands if c.startswith(first) and len(c) <= 120 and not PRICE_RE.search(c) and not NOISE_RE.search(c)]
        return (max(longer, key=len) if longer else first)[:120], company
    good = [c for c in cands if not is_company_name(c) and not PRICE_RE.search(c) and not NOISE_RE.search(c) and len(c) <= 120]
    if good:
        return max(good, key=len)[:120], company
    head = re.split(r"[¥￥]", clean, 1)[0].strip()
    head = re.split(r"[｜|]", head, 1)[0].strip()
    head = NOISE_RE.split(head)[0].strip()
    return (head[:120] if head and not is_company_name(head) else ""), company


def _json_after(html: str, key: str, max_len: int = 400_000):
    """html 안의 '"key":' 뒤에 오는 JSON 값(객체/배열)을 괄호 짝을 맞춰 잘라 파싱. 없거나 깨지면 None."""
    import json as _json

    i = html.find(f'"{key}":')
    if i < 0:
        return None
    j = i + len(key) + 3
    while j < len(html) and html[j] in " \t\r\n":
        j += 1
    if j >= len(html) or html[j] not in "[{":
        return None
    open_ch, close_ch = html[j], ("]" if html[j] == "[" else "}")
    depth, k, in_str, esc = 0, j, False, False
    while k < len(html) and k - j < max_len:
        ch = html[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(html[j:k + 1].replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&"))
                    except Exception:
                        return None
        k += 1
    return None


def parse_embedded(html: str) -> dict:
    """1688 상세 페이지의 내장 JSON 에서 구조화 값을 뽑는다. 못 찾은 키는 빠진다 (DOM/텍스트 폴백이 채움)."""
    out: dict = {}
    m = re.search(r'"offerTitle":"((?:[^"\\]|\\.)*)"', html)
    if m:
        out["title"] = m.group(1).encode().decode("unicode_escape", errors="ignore") if "\\u" in m.group(1) else m.group(1)
    for key in ("postCategoryId", "catId"):
        m = re.search(rf'"{key}":(\d+)', html)
        if m:
            out["cat_id"] = m.group(1)
            break
    m = re.search(r'"companyName":"((?:[^"\\]|\\.)*)"', html)
    if m:
        out["company"] = m.group(1)
    prices = _json_after(html, "currentPrices")
    if isinstance(prices, list) and prices:
        by_qty: dict[int, float] = {}
        for p in prices:
            try:
                q, v = int(str(p.get("beginAmount", 1)).strip() or 1), float(str(p.get("price")).replace(",", ""))
            except Exception:
                continue
            by_qty[q] = min(v, by_qty.get(q, v))
        out["tiers"] = [{"min_qty": q, "unit_price": v} for q, v in sorted(by_qty.items())]
    skus = _json_after(html, "skuInfoMap")
    if isinstance(skus, dict) and skus:
        opts = []
        for name, s in skus.items():
            try:
                opts.append({"sku_id": str(s.get("skuId") or s.get("specId") or ""), "name_raw": name, "price": float(str(s.get("discountPrice") or s.get("price") or 0) or 0),
                             "stock": int(s.get("canBookCount") or 0), "sold_out": int(s.get("canBookCount") or 0) <= 0, "sale_count": int(s.get("saleCount") or 0)})
            except Exception:
                continue
        out["options"] = opts
        if "tiers" not in out:
            ps = [o["price"] for o in opts if o["price"] > 0]
            if ps:
                out["tiers"] = [{"min_qty": 1, "unit_price": min(ps)}]
    pw = _json_after(html, "pieceWeightScaleInfo")
    if isinstance(pw, list) and pw:
        ws = [float(x.get("weight") or 0) for x in pw if x.get("weight")]
        if ws:
            out["weight_g"] = max(ws)  # 옵션 중 가장 무거운 것 (배대지 요금 보수적으로)
        dims = [x for x in pw if x.get("length")]
        if dims:
            d0 = dims[0]
            out["dims_cm"] = [float(d0.get("length") or 0), float(d0.get("width") or 0), float(d0.get("height") or 0)]
    imgs = _json_after(html, "mainImageList")
    if isinstance(imgs, list) and imgs:
        out["images"] = [x.get("fullPathImageURI") for x in imgs if x.get("fullPathImageURI")]
    return out


def parse_attr_text(text: str) -> dict[str, str]:
    """innerText 의 '商品属性' 구간을 '키 \\n 값' 쌍으로. 2열 표라 dt/dd 쌍이 안 맞는 DOM 파싱의 대안."""
    i = text.find("商品属性")
    if i < 0:
        return {}
    seg = text[i + 4:]
    for stop in ("展开全部", "包装信息", "商品详情"):
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
    lines = [ln.strip() for ln in seg.replace("\t", "\n").splitlines()]
    lines = [ln for ln in lines if ln]
    attrs: dict[str, str] = {}
    k = 0
    while k + 1 < len(lines):
        key, val = lines[k], lines[k + 1]
        if 1 <= len(key) <= 12 and len(val) <= 120 and key not in attrs:
            attrs[key] = val
            k += 2
        else:
            k += 1
    return attrs


def parse_tags(text: str) -> list[str]:
    """'商机组货：茶杯保温杯' 같은 카테고리 힌트 태그."""
    return [m.strip() for m in re.findall(r"商机组货[:：]\s*([^¥￥｜|]{2,30}?)(?=\s[¥￥]|\s*$|\s{2})", text)]

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


# 검색 카드의 가격은 "¥ 5 .9" 처럼 정수부와 소수부 사이에 공백이 들어간다 (DOM 이 둘을 다른 span 에 그림)
_PRICE_NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\s*\.\s*(\d+))?"


def _join_num(whole: str, frac: str | None) -> float:
    return float(whole.replace(",", "") + ("." + frac if frac else ""))


def parse_price(text: str) -> tuple[str, list[dict]]:
    """'¥12.50-15.00' · '¥ 5 .9' · '¥12.5 2件起批' 등에서 (원문, tiers). 구간은 최저가를 1구간 단가로."""
    m = re.search(r"[¥￥]\s*" + _PRICE_NUM + r"(?:\s*[-~～]\s*[¥￥]?\s*" + _PRICE_NUM + r")?", text)
    if not m:
        return "", []
    raw = " ".join(m.group(0).split())
    low = _join_num(m.group(1), m.group(2))
    tiers = [{"min_qty": 1, "unit_price": low}]
    # "≥2件 ¥12.5 ≥10件 ¥11.8" 식 다단가
    multi = re.findall(r"[≥>]\s*(\d+)\s*[件个套双条盒包]\s*[¥￥]\s*" + _PRICE_NUM, text)
    if multi:
        tiers = [{"min_qty": int(q), "unit_price": _join_num(w, f)} for q, w, f in multi]
    return raw, tiers


def parse_moq(text: str) -> int:
    m = re.search(r"(\d+)\s*[件个套双条盒包张只]\s*起批", text) or re.search(r"起批量?\s*[:：]?\s*(\d+)", text) or re.search(r"≥\s*(\d+)\s*[件个套]", text)
    return int(m.group(1)) if m else 1


def parse_sales(text: str) -> int | None:
    """'成交300件' · '全网4.8万+件' · '800+件' · '10万+件' → 정수."""
    m = re.search(r"(?:成交|已售|销量|全网)\s*([\d.]+)\s*(万)?\s*\+?\s*[件个套]", text) or re.search(r"(?<![\d.])([\d.]+)\s*(万)?\s*\+\s*[件个套]", text)
    if not m:
        return None
    return int(float(m.group(1)) * (10000 if m.group(2) else 1))


def card_to_listing(c: dict) -> RawListing | None:
    t = c.get("text", "")
    price_raw, tiers = parse_price(t)
    if not price_raw:
        return None
    cands = list(c.get("titles") or ([c["title"]] if c.get("title") else []))
    title, company = pick_title(cands, t)
    if not title:
        return None
    img = c.get("img", "")
    img = re.sub(r"_\.(avif|webp)$", "", img)
    img = re.sub(r"\.(jpg|png)_\d+x\d+(?:q\d+)?\.(?:jpg|png)$", r".\1", img)   # 썸네일 접미사 제거 → 원본
    ext = {}
    if company:
        ext["company"] = company
    sales = parse_sales(t)
    if sales is not None:
        ext["sales"] = sales
    tags = parse_tags(t)
    if tags:
        ext["tags"] = tags
    mp = re.search(r"(红包价|新人价|拿样价|批发价)", t)
    if mp:
        ext["price_label"] = mp.group(1)
    if "包邮" in t:
        ext["free_shipping"] = True
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
            self._dump_debug("blocked")
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
        if not out:
            self._dump_debug("list")
        return out

    def _dump_debug(self, tag: str) -> None:
        """카드 0건 등 이상 상황: URL · 제목 · 링크 수 · 본문 앞부분을 출력하고 스크린샷 · HTML 을 data/debug/ 에 남긴다."""
        try:
            from app.config import settings

            d = self.page.evaluate(JS_DIAG)
            print(f"[진단] url={d['url'][:120]}\n[진단] title={d['title'][:80]} · offer 링크 {d['offers']}개 · 이미지 {d['imgs']}장\n[진단] text={d['text'][:300]}")
            out = settings.data_dir / "debug"
            out.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.page.screenshot(path=str(out / f"1688_{tag}_{stamp}.png"), full_page=False)
            (out / f"1688_{tag}_{stamp}.html").write_text(self.page.content(), encoding="utf-8")
            print(f"[진단] 저장 {out / f'1688_{tag}_{stamp}.png'} · .html")
        except Exception as e:
            print(f"[진단] 실패 {type(e).__name__}: {e}")

    def login(self, wait_seconds: int = 600) -> bool:
        """헤드풀 창에서 사용자가 직접 로그인하도록 두고, Enter 또는 로그인 감지까지 기다린다. 프로필에 쿠키가 남는다."""
        if not self.headed:
            raise RuntimeError("--login 은 --headed 와 함께")
        self._goto_soft("https://login.1688.com/member/signin.htm")
        print("창에서 1688 에 로그인하세요 (QR · 휴대폰 인증 · 슬라이더). 끝나면 이 콘솔에서 Enter 를 누르세요.")
        for attempt in range(6):
            try:
                input()
            except EOFError:
                self.page.wait_for_timeout(wait_seconds * 1000)
            self._goto_soft("https://www.1688.com/")
            url = self.page.url
            body = ""
            try:
                body = (self.page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''") or "")
            except Exception:
                pass
            if "login_unusual" in url or "login.taobao.com" in url or "login.1688.com" in url or "passport.alibaba.com" in url:
                print(f"아직 로그인/추가 인증 페이지입니다 ({url[:70]}…). 창에서 인증(휴대폰 · 슬라이더 · 비정상 로그인 확인)을 마치고 다시 Enter 를 누르세요. ({attempt + 1}/6)")
                continue
            ok = any(k in body for k in ("退出", "我的1688", "我的阿里", "消息", "采购车")) and "免费注册" not in body[:300]
            print("로그인 확인:", "성공 (프로필 저장됨)" if ok else f"확인 못 함 — 현재 페이지 {url[:80]} · 창에서 로그인 상태를 다시 보고 Enter")
            if ok:
                return True
        return False

    def _goto_soft(self, url: str) -> None:
        """리다이렉트(추가 인증 페이지 등)로 이동이 가로채여도 예외 없이 자리를 잡을 때까지 기다린다."""
        try:
            self.page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:  # "interrupted by another navigation" 류
            if "interrupted" not in str(e).lower() and "navigation" not in str(e).lower():
                raise
        for _ in range(3):
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                break
            except Exception:
                pass
        self.page.wait_for_timeout(2500)

    def detail(self, item_url: str) -> RawDetail:
        time.sleep(random.uniform(*self.delay_range))
        self._goto(item_url, wait_ms=3000)
        for y in (800, 1800, 3000, 0):
            self.page.mouse.wheel(0, y)
            self.page.wait_for_timeout(300)
        data = self.page.evaluate(JS_DETAIL)
        text = data.get("text") or ""
        emb = parse_embedded(self.page.content())
        return build_detail(item_url, text, data, emb)


def build_detail(item_url: str, text: str, data: dict, emb: dict) -> RawDetail:
    """상세 페이지의 내장 JSON(emb) 을 우선, 없으면 innerText · DOM 으로 RawDetail 을 만든다. 순수 함수 — 저장한 HTML 로 테스트 가능."""
    m = OFFER_RE.search(item_url)
    attrs = parse_attr_text(text) or (data.get("attrs") or {})
    tiers = emb.get("tiers") or []
    price_raw = ""
    if tiers:
        price_raw = "¥" + "/".join(f"{t['unit_price']:g}" for t in tiers[:3])
    else:
        # 텍스트 폴백: '券后 ¥0.90起' 같은 쿠폰가는 건너뛰고 SKU 행의 '¥9.5' 를 쓴다
        prices = [float(x) for x in re.findall(r"[¥￥]\s*(\d+(?:\.\d+)?)\s*(?:\n|\s)*库存", text)]
        if prices:
            tiers = [{"min_qty": 1, "unit_price": min(prices)}]
            price_raw = f"¥{min(prices):g}"
        else:
            price_raw, tiers = parse_price(text)
    weight_g = emb.get("weight_g")
    weight_raw = f"{weight_g:g}g" if weight_g else (attrs.get("重量") or attrs.get("毛重") or attrs.get("净重") or "")
    images = emb.get("images") or [re.sub(r"_\.(avif|webp)$", "", u) for u in (data.get("imgs") or [])]
    main_img = images[0] if images else ((data.get("metas") or {}).get("og:image") or "")
    moq = min([t["min_qty"] for t in tiers] or [parse_moq(text)])
    moq = max(moq, parse_moq(text)) if "起批" in text else moq
    ext: dict = {}
    sales = parse_sales(text)
    if sales is not None:
        ext["sales"] = sales
    if emb.get("company"):
        ext["company"] = emb["company"]
    if emb.get("cat_id"):
        ext["cat_id_1688"] = emb["cat_id"]
    if emb.get("dims_cm"):
        ext["dims_cm"] = emb["dims_cm"]
    options = emb.get("options") or []
    sold_out = ("已下架" in text or "商品不存在" in text) or (bool(options) and all(o.get("sold_out") for o in options))
    return RawDetail(
        source_id="1688", item_id=m.group(1) if m else item_url, url=item_url,
        title_raw=emb.get("title") or (data.get("metas") or {}).get("og:title") or (data.get("title") or "").split(" - ")[0], lang="zh",
        price_raw=price_raw, price_tiers=tiers, currency="CNY", moq=moq, image_url=main_img,
        category_raw=" > ".join(data.get("crumbs") or []), attrs_raw=attrs, weight_raw=weight_raw, sold_out=sold_out,
        images=images[:30], attrs_full=attrs, package_weight_raw=weight_raw,
        options=[{"sku_id": o["sku_id"], "name_raw": o["name_raw"], "price": o["price"], "sold_out": o["sold_out"]} for o in options][:60],
        extra=ext,
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
    ap.add_argument("url", nargs="?")
    ap.add_argument("--profile", default="1688")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--login", action="store_true", help="창을 띄워 로그인만 하고 프로필 저장 (--headed 필요)")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--detail", action="store_true", help="상세 1건")
    ap.add_argument("-o", "--out", help="JSON 저장 경로 (규칙 생성기 샘플)")
    a = ap.parse_args(argv)
    if a.login:
        with Adapter1688(profile_dir=settings.profiles_dir / a.profile, headed=True) as ad:
            return 0 if ad.login() else 1
    if not a.url:
        ap.print_help()
        return 1
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
            print(json.dumps({"item_id": r["item_id"], "title_raw": r["title_raw"], "price_raw": r["price_raw"], "moq": r["moq"],
                              "company": (r.get("extra") or {}).get("company"), "sales": (r.get("extra") or {}).get("sales")}, ensure_ascii=False))
        print(f"… 총 {len(rows)}건")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
