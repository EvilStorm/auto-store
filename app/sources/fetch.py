"""상품 페이지 스냅샷 수집기 (Playwright).

LLM 추출 어댑터의 입력을 만든다: 보이는 텍스트 + 이미지 URL 목록 + 메타.
소스별 셀렉터 없이 어느 사이트든 동작하는 것이 목적이고, 내장 어댑터는 나중에 이 위에 얹는다.
로그인 유지가 필요한 소스(1688 등)는 profile_dir 로 persistent context 를 쓴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

MAX_TEXT_CHARS = 14000
MAX_IMAGES = 16

JS_COLLECT = """
() => {
  const metas = {};
  for (const m of document.querySelectorAll('meta[property], meta[name]')) {
    const k = m.getAttribute('property') || m.getAttribute('name');
    const v = m.getAttribute('content');
    if (k && v && (k.startsWith('og:') || k === 'description' || k === 'keywords')) metas[k] = v;
  }
  const imgs = [];
  const seen = new Set();
  for (const img of document.images) {
    let src = img.currentSrc || img.src || img.getAttribute('data-src') || '';
    if (!src || src.startsWith('data:')) continue;
    if (img.naturalWidth && img.naturalWidth < 200) continue;
    const r = img.getBoundingClientRect();
    if (r.width && r.width < 120) continue;
    if (seen.has(src)) continue;
    seen.add(src);
    imgs.push({src, w: img.naturalWidth || Math.round(r.width), h: img.naturalHeight || Math.round(r.height), alt: img.alt || ''});
  }
  const text = (document.body && document.body.innerText) || '';
  return {title: document.title, metas, imgs, text, url: location.href};
}
"""


@dataclass
class PageSnapshot:
    requested_url: str
    final_url: str
    host: str
    title: str
    text: str
    images: list[str] = field(default_factory=list)
    og_image: str = ""
    metas: dict = field(default_factory=dict)
    blocked_hint: str = ""

    def main_image(self) -> str:
        return self.og_image or (self.images[0] if self.images else "")


BLOCK_PATTERNS = [
    ("captcha", "캡차"),
    ("verify", "인증 요구"),
    ("滑动验证", "슬라이더 캡차"),
    ("请完成安全验证", "보안 인증"),
    ("access denied", "접근 거부"),
    ("login", "로그인 요구"),
]


NOT_FOUND_PATTERNS = ("찾으시는 페이지가 없습니다", "page not found", "页面不存在", "商品不存在", "该商品已下架", "sorry, this item is no longer available")


def _detect_block(title: str, text: str, requested_url: str = "", final_url: str = "") -> str:
    probe = (title + " " + text[:3000]).lower()
    for pat in NOT_FOUND_PATTERNS:
        if pat.lower() in probe:
            return "상품 페이지 없음 (삭제되었거나 잘못된 URL)"
    # 상품 상세 URL 을 요청했는데 홈/목록으로 튕긴 경우
    if requested_url and final_url:
        rp, fp = urlparse(requested_url).path, urlparse(final_url).path
        if rp not in ("", "/") and fp in ("", "/", "/index.html"):
            return "홈으로 리다이렉트됨 (상품 없음 · 로그인 필요 · 차단 중 하나)"
    if len(text.strip()) < 200:
        for pat, label in BLOCK_PATTERNS:
            if pat in probe:
                return label
        return "본문이 거의 비어 있음 (차단 또는 로딩 실패 가능)"
    return ""


def _normalize_image_url(u: str) -> str:
    """알리바바 계열 CDN 의 avif/webp 변환 접미사를 떼어 LLM 이 읽을 수 있는 jpg/png 원본 URL 로 만든다."""
    u = re.sub(r"_\.(avif|webp)$", "", u)
    return u


def _is_tracker(u: str) -> bool:
    return any(k in u for k in ("bat.bing.com", "doubleclick", "/action/0?", "pixel", "beacon"))


def _clean_text(t: str) -> str:
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()[:MAX_TEXT_CHARS]


def fetch_page(url: str, *, profile_dir: Path | None = None, headed: bool = False, wait_ms: int = 2500) -> PageSnapshot:
    from app import browser as br

    host = urlparse(url).netloc
    with sync_playwright() as p:
        if profile_dir:
            ctx = br.launch_persistent(
                p,
                profile_dir,
                headless=not headed,
                locale="zh-CN",
                viewport={"width": 1366, "height": 900},
            )
            browser = None
        else:
            browser = br.launch(p, headless=not headed)
            ctx = browser.new_context(
                locale="zh-CN",
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
            )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PWTimeout:
                pass
            # 지연 로딩 이미지를 위해 한 번 스크롤
            for y in (600, 1400, 2400, 0):
                page.mouse.wheel(0, y)
                page.wait_for_timeout(300)
            page.wait_for_timeout(wait_ms)
            data = page.evaluate(JS_COLLECT)
        finally:
            ctx.close()
            if browser:
                browser.close()

    text = _clean_text(data.get("text") or "")
    metas = data.get("metas") or {}
    imgs = []
    for i in sorted(data.get("imgs") or [], key=lambda i: -(i["w"] * i["h"])):
        u = _normalize_image_url(i["src"])
        if u and u not in imgs and not _is_tracker(u):
            imgs.append(u)
        if len(imgs) >= MAX_IMAGES:
            break
    if metas.get("og:image"):
        metas["og:image"] = _normalize_image_url(metas["og:image"])
    snap = PageSnapshot(
        requested_url=url,
        final_url=data.get("url") or url,
        host=host,
        title=data.get("title") or "",
        text=text,
        images=imgs,
        og_image=metas.get("og:image", ""),
        metas=metas,
    )
    snap.blocked_hint = _detect_block(snap.title, snap.text, snap.requested_url, snap.final_url)
    return snap
