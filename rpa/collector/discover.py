"""인기 상품 찾기 (주 1회): robots.txt가 허용하는 다나와 카테고리 목록 페이지에서 상위 상품 코드를 읽어 우선순위 후보를 만든다.

- 목록 페이지(prod.danawa.com/list/?cate=…)의 기본 정렬은 인기상품순이며, HTML에 들어 있는 순서를 순위로 쓴다.
- 금지 경로(/list/ajax/)는 호출하지 않는다. robots.txt가 막으면 그 카테고리는 건너뛴다.
- 결과는 후보 목록(JSON)으로만 저장한다. 에누리와 같은 제품인지 확인한 뒤 catalog.json에 넣는다(자동 등록하지 않음).
실행: python -m collector.discover [출력 파일]
"""
import json
import re
import sys
from pathlib import Path

from .config import Config
from .http import CollectError, PoliteSession
from .parsers import parse_jsonld_offer

CATEGORIES = {"노트북": "112758", "모니터": "112757", "무선이어폰": "12227953", "공기청정기": "10248425", "그래픽카드": "112753"}
TOP_N = 10
PCODE = re.compile(r"prod\.danawa\.com/info/\?pcode=(\d{6,})")


def ranked_codes(html: str, top: int = TOP_N) -> list[str]:
    """목록 HTML에 나타난 순서대로 중복 없는 상품 코드 상위 top개"""
    return list(dict.fromkeys(PCODE.findall(html)))[:top]


def discover(cfg: Config | None = None, top: int = TOP_N) -> list[dict]:
    cfg = cfg or Config()
    out: list[dict] = []
    with PoliteSession(cfg.user_agent, cfg.request_interval_sec) as s:
        for name, cate in CATEGORIES.items():
            url = f"https://prod.danawa.com/list/?cate={cate}"
            try:
                codes = ranked_codes(str(s.fetch(url)), top)
            except CollectError as exc:  # robots.txt 금지·접근 거부는 건너뛴다(우회하지 않음)
                print(f"건너뜀 {name}: {exc}", file=sys.stderr)
                continue
            for rank, code in enumerate(codes, 1):
                detail = s.fetch(f"https://prod.danawa.com/info/?pcode={code}")
                title = detail.title.get_text(strip=True).split(":")[0].strip() if detail.title else ""
                price = parse_jsonld_offer(detail)
                if price["in_stock"]:
                    out.append({"category": name, "rank": rank, "priority": (TOP_N - rank + 1) * 10, "danawa_pcode": code,
                                "name": title, "price": price["price"]})
    return out


if __name__ == "__main__":
    result = discover()
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/discovered.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"후보 {len(result)}개 → {path}")
