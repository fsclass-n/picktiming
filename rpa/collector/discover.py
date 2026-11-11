"""인기 상품 찾기 (주 1회): robots.txt가 허용하는 다나와 카테고리 목록 페이지에서 상위 상품 코드를 읽어 우선순위 후보를 만든다.

- 목록 페이지(prod.danawa.com/list/?cate=…)의 기본 정렬은 인기상품순이며, HTML에 들어 있는 순서를 순위로 쓴다.
- 금지 경로(/list/ajax/)는 호출하지 않는다. robots.txt가 막으면 그 카테고리는 건너뛴다.
- 에누리 대조: 에누리 검색(price.enuri.com/search, robots 허용)으로 후보를 찾고, 에누리 상세 페이지의 상품명(옵션 포함)과
  사양 요약이 다나와와 같을 때만 enuri_modelno를 채운다(공백·괄호 모양 차이만 무시).
- 결과는 후보 목록(JSON)으로만 저장한다. 사람이 확인한 뒤 catalog.json에 넣는다(자동 등록하지 않음). 이미 카탈로그에 있는 상품은 건너뛴다.
실행: python -m collector.discover [출력 파일]
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from .config import Config
from .http import CollectError, PoliteSession
from .parsers import jsonld_items, parse_jsonld_offer

# 세부 카테고리 15개: 이름 → (다나와 카테고리 코드, 서비스 분류). 코드는 2026-11-10 카탈로그 상품 페이지의 BreadcrumbList에서 확인
# 목록은 첫 페이지만 쓴다(다음 페이지는 robots.txt 금지 경로 /list/ajax/) → 카테고리당 최대 TOP_N개(포장 수량만 다른 같은 제품은 1개)
CATEGORIES = {
    "노트북": ("112758", "디지털"), "모니터": ("112757", "디지털"), "무선이어폰": ("12237349", "디지털"), "무선헤드폰": ("12237350", "디지털"),
    "스마트폰": ("122515", "디지털"), "태블릿": ("122577", "디지털"), "그래픽카드": ("112753", "디지털"),
    "마우스": ("112787", "디지털"), "미러리스": ("12237505", "디지털"),
    "TV": ("10248425", "가전"), "공기청정기": ("10352481", "가전"), "무선청소기": ("102207", "가전"), "에어프라이어": ("10252979", "가전"),
    "압력밥솥": ("10252932", "가전"),
    "생수": ("1623153", "생필품"), "롤화장지": ("1723788", "생필품"), "날면도기": ("10348402", "생필품"),
    "기저귀": ("16249105", "유아"), "분유": ("16249091", "유아"),
}
TOP_N = 40
ENURI_CANDIDATES = 3  # 에누리 검색 결과 중 상세 페이지까지 확인할 개수
PCODE = re.compile(r"prod\.danawa\.com/info/\?pcode=(\d{6,})")
ENURI_MODEL = re.compile(r"detail\.jsp\?modelno=(\d+)")


def ranked_codes(html: str, top: int = TOP_N) -> list[str]:
    """목록 HTML에 나타난 순서대로 중복 없는 상품 코드 상위 top개"""
    return list(dict.fromkeys(PCODE.findall(html)))[:top]


def norm(text: str | None) -> str:
    """비교용: 공백 제거, [옵션]·(옵션) 괄호 통일, 소문자"""
    return re.sub(r"\s+", "", (text or "")).replace("[", "(").replace("]", ")").lower()


def product_ld(soup) -> dict:
    return next((i for i in jsonld_items(soup) if i.get("@type") == "Product"), {})


SPEC_OVERLAP = 0.8  # 에누리 사양 항목 중 다나와에도 있어야 하는 비율(에누리는 '코드리스' 같은 항목 몇 개를 빼고 보여 준다)
NOT_NEW = re.compile(r"중고|해외구매|리퍼|렌탈|구독")  # 새 정품이 아닌 다나와 항목은 후보에서 뺀다


PACK = re.compile(r"\s*\((?:\d[\d,]*\s*(?:개|팩|매|롤|입|박스|세트|ea)|\d+롤\s*x\s*\d+팩)\)", re.I)


def base_name(name: str | None) -> str:
    """포장 수량 괄호를 뺀 제품 이름. '삼다수 그린 2L (24개)'와 '(6개)'는 같은 제품 → 후보는 순위가 가장 높은 1개만 남긴다"""
    return norm(PACK.sub("", name or ""))


def spec_tokens(text: str | None) -> list[str]:
    return [t for t in norm(text).split("/") if t]


def same_product(danawa: dict, enuri: dict) -> bool:
    """상품명(옵션 포함)이 같고, 제품 종류(사양 첫 항목)가 같으며, 에누리 사양 항목의 80% 이상이 다나와 사양에도 있을 때만 같은 제품으로 본다"""
    d, e = spec_tokens(danawa.get("description")), spec_tokens(enuri.get("description"))
    if not (d and e and norm(danawa.get("name")) == norm(enuri.get("name")) and d[0] == e[0]):
        return False
    return sum(t in set(d) for t in e) / len(e) >= SPEC_OVERLAP


def enuri_search_models(html: str) -> list[str]:
    """에누리 검색 결과(JSON-LD ItemList, 정확도순)의 가격비교 상품 modelno. 쇼핑몰 단독 상품(긴 번호)은 상세 비교 대상이 아니라서 뺀다"""
    return [m for m in dict.fromkeys(ENURI_MODEL.findall(html)) if len(m) <= 9]


def match_enuri(s: PoliteSession, danawa: dict) -> str | None:
    """다나와 상품과 같은 에누리 modelno(정확히 하나일 때만)"""
    keyword = re.sub(r"[()\[\],]", " ", danawa.get("name") or "").split()  # 옵션(SSD 용량 등)까지 검색어에 넣어 같은 구성이 위로 오게 한다
    keyword = " ".join(keyword)
    found = []
    for m in enuri_search_models(str(s.fetch(f"https://price.enuri.com/search?keyword={quote(keyword)}")))[:ENURI_CANDIDATES]:
        if same_product(danawa, product_ld(s.fetch(f"https://www.enuri.com/detail.jsp?modelno={m}"))):
            found.append(m)
    return found[0] if len(found) == 1 else None


def discover(cfg: Config | None = None, top: int = TOP_N, categories: dict | None = None) -> list[dict]:
    cfg = cfg or Config()
    products = cfg.catalog().get("products", [])
    have = {c for p in products for l in p.get("listings", []) for c in PCODE.findall(l.get("url", ""))}
    bases = {base_name(p.get("name")) for p in products}
    out: list[dict] = []
    with PoliteSession(cfg.user_agent, cfg.request_interval_sec) as s:
        for name, (cate, site_category) in (categories or CATEGORIES).items():
            try:
                codes = ranked_codes(str(s.fetch(f"https://prod.danawa.com/list/?cate={cate}")), top)
            except CollectError as exc:  # robots.txt 금지·접근 거부는 건너뛴다(우회하지 않음)
                print(f"건너뜀 {name}: {exc}", file=sys.stderr)
                continue
            for rank, code in enumerate(codes, 1):
                if code in have:
                    continue
                try:
                    detail = s.fetch(f"https://prod.danawa.com/info/?pcode={code}")
                    ld, price = product_ld(detail), parse_jsonld_offer(detail)
                    if not price["in_stock"] or NOT_NEW.search(ld.get("name") or "") or base_name(ld.get("name")) in bases:
                        continue
                    bases.add(base_name(ld.get("name")))
                    enuri = match_enuri(s, ld)
                except CollectError as exc:
                    print(f"건너뜀 {name} {code}: {exc}", file=sys.stderr)
                    continue
                out.append({"category": name, "site_category": site_category, "rank": rank, "priority": (top - rank + 1) * 10,
                            "danawa_pcode": code, "name": ld.get("name") or "", "spec": ld.get("description") or "",
                            "image": ld.get("image") if isinstance(ld.get("image"), str) else None,
                            "price": price["price"], "enuri_modelno": enuri})
                print(f"{name} {rank}위 {code} 에누리={enuri}", file=sys.stderr, flush=True)
    return out


if __name__ == "__main__":
    result = discover()
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/discovered.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"후보 {len(result)}개(에누리 일치 {sum(bool(r['enuri_modelno']) for r in result)}개) → {path}")
