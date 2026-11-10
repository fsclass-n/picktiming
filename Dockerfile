# [전환·롤백용] 이전 Render 통합 이미지: FastAPI + React 빌드 결과를 같은 도메인으로 제공
# Render는 이제 분리 배포한다(render.yaml): 백엔드 = backend/Dockerfile(API 전용), 프런트엔드 = Static Site.
# 이 파일은 대시보드 Dockerfile Path를 ./backend/Dockerfile로 바꾸기 전까지의 전환 기간과, 문제 시 되돌리기(Dockerfile Path → ./Dockerfile)에만 쓴다.
# 분리 배포가 안정되면 삭제해도 된다(CI의 '이전 통합 이미지' 단계와 함께). 빌드 컨텍스트는 저장소 루트(.).
#   docker build -t timepick-render .
# 1단계: React 빌드
FROM node:22-alpine AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2단계: FastAPI + 빌드 결과(dist)
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul \
    FRONTEND_DIR=/app/frontend

# fonts-nanum: 주간 리포트(Seaborn·Matplotlib) 한글 차트, curl: 헬스 체크
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-nanum curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=web /src/dist ./frontend
RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1
# Render는 PORT 환경 변수를 주입한다(기본 10000).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
