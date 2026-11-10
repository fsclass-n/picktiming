"""TimePick API의 RPA 수신 엔드포인트(X-RPA-KEY) 클라이언트"""
from datetime import datetime

import requests


class ApiClient:
    def __init__(self, base_url: str, rpa_key: str, timeout: float = 60):
        self.base = f"{base_url.rstrip('/')}/api/v1/rpa"
        self.s = requests.Session()
        self.s.headers.update({"X-RPA-KEY": rpa_key})
        self.timeout = timeout

    def _req(self, method: str, path: str, **kw):
        r = self.s.request(method, self.base + path, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def ensure_listings(self, name: str, base_url: str, url_template: str) -> dict:
        """쇼핑몰(예: 네이버쇼핑)과 모든 상품의 판매처를 없으면 만든다"""
        return self._req("POST", "/ensure-listings", json={"name": name, "base_url": base_url, "url_template": url_template}).json()

    def sync_catalog(self, catalog: dict) -> dict:
        """실제 수집 상품·판매처(rpa/catalog.json)를 DB에 맞춘다. 시연용 쇼핑몰은 retire_mall_hosts로 비활성화"""
        return self._req("PUT", "/catalog", json=catalog).json()

    def listings(self) -> list[dict]:
        return self._req("GET", "/listings").json()["items"]

    def post_prices(self, items: list[dict], collected_at: datetime) -> dict:
        return self._req("POST", "/prices/bulk", json={"collected_at": collected_at.isoformat(), "items": items}).json()

    def put_public_prices(self, items: list[dict]) -> dict:
        return self._req("PUT", "/public-prices", json={"items": items}).json()

    def log(self, job_name: str, status: str, started_at: datetime, ended_at: datetime, collected=0, failed=0, message=None) -> None:
        self._req("POST", "/logs", json={"job_name": job_name, "status": status, "collected": collected, "failed": failed,
                                         "message": (message or "")[:500], "started_at": started_at.isoformat(),
                                         "ended_at": ended_at.isoformat()})

    def train(self) -> dict:
        return self._req("POST", "/train").json()

    def weekly_report(self) -> tuple[bytes, str]:
        r = self._req("GET", "/reports/weekly")
        name = r.headers.get("Content-Disposition", "").split("filename=")[-1].strip('"') or "weekly_report.xlsx"
        return r.content, name
