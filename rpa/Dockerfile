# RPA 수집기 이미지 (EC2 docker compose의 rpa 서비스). 빌드 컨텍스트 = 저장소 루트
#   docker build -f rpa/Dockerfile -t timepick-rpa .
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY requirements.txt .
# Playwright Chromium: JavaScript로 가격을 그리는 쇼핑몰(malls.json "render": "playwright")용
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY rpa/collector ./collector
COPY rpa/malls.json rpa/catalog.json rpa/public_price_map.json ./
RUN useradd --create-home rpa && mkdir -p /app/reports && chown -R rpa /app /ms-playwright
USER rpa

# 기본: 내장 스케줄러(03:00 재학습, 06:00 참가격, 월 07:00 리포트. 외부 가격 수집은 COLLECT_ENABLED=true일 때만 — compose 기본 false)
# 단발 실행: docker compose run --rm rpa python -m collector.jobs collect
CMD ["python", "-m", "collector.scheduler"]
