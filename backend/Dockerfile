# FastAPI API 이미지 (EC2 compose의 api, CI). 빌드 컨텍스트 = 저장소 루트
#   docker build -f backend/Dockerfile -t timepick-api .
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

# fonts-nanum: 주간 리포트(Seaborn·Matplotlib) 한글 차트, curl: 헬스 체크
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-nanum curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1
# Render는 PORT 환경 변수를 주입한다(기본 10000). EC2에서는 8000 사용.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
