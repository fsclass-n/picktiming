"""예의 있는 수집 요청: robots.txt 확인 · 사이트별 요청 간격(robots Crawl-delay 반영) · 3회 재시도(지수 백오프)

차단을 우회하지 않는다: 봇 이름을 그대로 밝히고(User-Agent 위장·IP 교체 없음), 403·429·CAPTCHA는 실패로 기록한 뒤 다음 주기에 다시 시도한다.
"""
import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
NO_RETRY = {401, 403, 404, 410, 429}  # 거부·없음·요청 과다는 같은 실행 안에서 다시 두드리지 않는다


class CollectError(Exception):
    pass


class PoliteSession:
    def __init__(self, user_agent: str, interval_sec: float = 3.0, retries: int = 3, timeout: float = 10.0):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9"})
        self.ua, self.interval, self.retries, self.timeout = user_agent, interval_sec, retries, timeout
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last: dict[str, float] = {}
        self._browser = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.__exit__(None, None, None)
            self._browser = None

    @staticmethod
    def _root(url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    def _rules(self, url: str) -> urllib.robotparser.RobotFileParser:
        root = self._root(url)
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(f"{root}/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse(["User-agent: *", "Disallow: /"])  # robots.txt를 확인할 수 없으면 수집하지 않는다
            self._robots[root] = rp
        return self._robots[root]

    def allowed(self, url: str) -> bool:
        return self._rules(url).can_fetch(self.ua, url)

    def delay_for(self, url: str) -> float:
        """사이트가 robots.txt에 Crawl-delay를 정했으면 기본 간격보다 길 때 그 값을 따른다"""
        rp = self._robots.get(self._root(url))
        delay = rp.crawl_delay(self.ua) if rp else None
        return max(self.interval, float(delay or 0))

    def wait(self, url: str = "") -> None:
        """같은 사이트끼리만 간격을 유지한다(다른 사이트 요청은 기다리지 않음). API 호출에도 같은 규칙 적용"""
        host = urlparse(url).netloc
        last = self._last.get(host)
        if last is not None:
            gap = self.delay_for(url) - (time.monotonic() - last)
            if gap > 0:
                time.sleep(gap)
        self._last[host] = time.monotonic()

    _wait = wait

    def _render(self, url: str, wait_for: str | None) -> BeautifulSoup:
        if self._browser is None:  # 수집 1회에 브라우저 1개만 띄워 재사용한다
            from .browser import BrowserSession

            self._browser = BrowserSession(self.ua, self.allowed, int(self.timeout * 2000)).__enter__()
        return self._browser.render(url, wait_for)

    def fetch(self, url: str, render: bool = False, wait_for: str | None = None) -> BeautifulSoup:
        """render=True면 Playwright(Chromium)로 JavaScript 실행 후의 HTML을 가져온다"""
        if not self.allowed(url):
            raise CollectError(f"robots.txt가 허용하지 않는 경로: {url}")
        for attempt in range(self.retries):
            self.wait(url)
            try:
                if render:
                    return self._render(url, wait_for)
                r = self.s.get(url, timeout=self.timeout)
                if r.status_code in NO_RETRY:
                    raise CollectError(f"HTTP {r.status_code} (접근 거부·요청 제한, 우회하지 않음): {url}")
                r.raise_for_status()
                return BeautifulSoup(r.text, "html.parser")
            except CollectError:
                raise
            except Exception as exc:  # requests 오류, Playwright 시간 초과 등
                log.warning("요청 실패(%s/%s) %s: %s", attempt + 1, self.retries, url, exc)
                time.sleep(3 * 2 ** attempt)
        raise CollectError(f"요청 실패: {url}")
