import json
import os
import pathlib
from dataclasses import dataclass, field

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() == "true"


@dataclass(frozen=True)
class Config:
    api_base_url: str = field(default_factory=lambda: os.getenv("RPA_TARGET_API", "http://localhost:8000").rstrip("/"))
    rpa_api_key: str = field(default_factory=lambda: os.getenv("RPA_API_KEY", ""))
    request_interval_sec: float = field(default_factory=lambda: float(os.getenv("REQUEST_INTERVAL_SEC", "3")))
    user_agent: str = field(default_factory=lambda: os.getenv("COLLECTOR_USER_AGENT", "TimePickBot/1.0 (+contact: team3@timepick.example)"))
    # 시연용 쇼핑몰(*.example.com) 모의 가격. 실제 수집 환경(GitHub Actions)은 false
    simulate: bool = field(default_factory=lambda: _flag("SIMULATE_MALLS", "true"))
    # 외부 사이트 가격 수집 여부. 실제 수집은 GitHub Actions 한 곳만 하고 EC2 rpa 컨테이너는 false(docker-compose.yml)
    collect_enabled: bool = field(default_factory=lambda: _flag("COLLECT_ENABLED", "true"))
    # 예약 실행용: 이번 KST 6시간 구간(0·6·12·18시 시작)에 이미 수집했으면 건너뛴다(GitHub 예약 실행이 불규칙해서)
    collect_if_due: bool = field(default_factory=lambda: _flag("COLLECT_IF_DUE", "false"))
    mall_config_path: pathlib.Path = field(default_factory=lambda: pathlib.Path(os.getenv("MALL_CONFIG", ROOT / "malls.json")))
    # 실제 수집 상품 목록(다나와 pcode·에누리 modelno). 수집 전에 API(PUT /rpa/catalog)로 DB와 맞춘다
    catalog_path: pathlib.Path = field(default_factory=lambda: pathlib.Path(os.getenv("CATALOG", ROOT / "catalog.json")))
    public_api_url: str = field(default_factory=lambda: os.getenv("KCA_API_URL", ""))
    public_api_key: str = field(default_factory=lambda: os.getenv("DATA_GO_KR_KEY", ""))
    public_map_path: pathlib.Path = field(default_factory=lambda: pathlib.Path(os.getenv("PUBLIC_PRICE_MAP", ROOT / "public_price_map.json")))
    report_dir: pathlib.Path = field(default_factory=lambda: pathlib.Path(os.getenv("REPORT_DIR", ROOT / "reports")))
    tz: str = field(default_factory=lambda: os.getenv("TZ", "Asia/Seoul"))
    # AWS S3 (선택) — 값이 있으면 수집 원본·주간 리포트를 업로드
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_prefix: str = field(default_factory=lambda: os.getenv("S3_PREFIX", "timepick").strip("/"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "ap-northeast-2"))

    @staticmethod
    def _load(path: pathlib.Path) -> dict:
        if not path.exists():
            return {}
        return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}  # _comment 등 설명 키 제외

    def mall_rules(self) -> dict:
        return self._load(self.mall_config_path)

    def catalog(self) -> dict:
        return self._load(self.catalog_path)
