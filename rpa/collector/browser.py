"""JavaScript로 가격을 그리는 쇼핑몰용 Headless Chromium 렌더링 (malls.json 규칙에 "render": "playwright")

- 수집 1회 동안 브라우저 1개를 재사용하고 페이지(탭)는 매번 닫는다 — 기동 시간·메모리 절약(무료 실행 환경 512MB~)
- 이미지·폰트·미디어, 다른 사이트(광고·분석)의 XHR, robots.txt가 금지한 같은 사이트 XHR(예: 다나와 /info/ajax/)은 보내지 않는다
- 브라우저는 GitHub Actions(collect-render.yml의 playwright install 단계)와 rpa Docker 이미지에 설치된다.
  로컬: python -m playwright install chromium
"""
from urllib.parse import urlparse

from bs4 import BeautifulSoup

BLOCKED_TYPES = {"image", "media", "font"}
# /dev/shm이 작은 컨테이너(Docker 기본 64MB)에서 탭이 죽지 않게 한다. Playwright는 기본으로 --no-sandbox 상태로 Chromium을 띄운다
LAUNCH_ARGS = ["--disable-dev-shm-usage", "--disable-gpu", "--no-first-run", "--mute-audio"]


class BrowserSession:
    def __init__(self, user_agent: str, allowed, timeout_ms: int = 20_000):
        self.ua, self.allowed, self.timeout = user_agent, allowed, timeout_ms  # allowed = PoliteSession.allowed(robots.txt)
        self._page_host = ""

    def __enter__(self):
        from playwright.sync_api import sync_playwright  # 필요한 경우에만 불러온다(무거운 의존성)

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
            self._ctx = self._browser.new_context(user_agent=self.ua, locale="ko-KR", timezone_id="Asia/Seoul",
                                                  viewport={"width": 1280, "height": 900})
            self._ctx.route("**/*", self._filter)
        except Exception:
            self._pw.stop()
            raise
        return self

    def _filter(self, route) -> None:
        req = route.request
        if req.resource_type in BLOCKED_TYPES:
            return route.abort()
        if req.resource_type in {"xhr", "fetch"}:
            same_site = urlparse(req.url).netloc == self._page_host
            if not same_site or not self.allowed(req.url):
                return route.abort()
        return route.continue_()

    def render(self, url: str, wait_for: str | None = None) -> BeautifulSoup:
        self._page_host = urlparse(url).netloc
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            if wait_for:
                page.wait_for_selector(wait_for, timeout=self.timeout)
            else:
                page.wait_for_load_state("networkidle", timeout=self.timeout)
            return BeautifulSoup(page.content(), "html.parser")
        finally:
            page.close()  # 탭은 매번 닫아 메모리 누적을 막는다

    def __exit__(self, *exc) -> None:
        for close in (self._ctx.close, self._browser.close, self._pw.stop):
            try:
                close()
            except Exception:  # 종료 중 오류는 수집 결과에 영향을 주지 않는다
                pass
