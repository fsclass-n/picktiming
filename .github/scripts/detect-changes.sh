#!/usr/bin/env bash
# deploy.yml용: 바뀐 경로를 보고 배포 대상을 GITHUB_OUTPUT에 기록한다.
# 입력(env): EVENT, BEFORE, EC2_MODE(full|rpa-only), IN_NETLIFY/IN_RENDER/IN_EC2(수동 실행 입력)
# 로컬 테스트: CHANGED_FILES="backend/app/main.py" EVENT=push bash .github/scripts/detect-changes.sh
set -euo pipefail

OUT="${GITHUB_OUTPUT:-/dev/stdout}"
EC2_MODE="${EC2_MODE:-full}"
ZERO=0000000000000000000000000000000000000000

emit() { echo "$1=$2" >> "$OUT"; }

if [ "${EVENT:-push}" = "workflow_dispatch" ]; then
  echo "수동 실행: 선택한 대상 전체 배포"
  emit netlify "${IN_NETLIFY:-true}"
  emit render "${IN_RENDER:-true}"
  emit ec2 "${IN_EC2:-true}"
  emit ec2_all true
  emit ec2_services ""
  emit ec2_web true
  exit 0
fi

if [ -n "${CHANGED_FILES:-}" ]; then
  files="$CHANGED_FILES"
elif [ -z "${BEFORE:-}" ] || [ "$BEFORE" = "$ZERO" ] || ! git cat-file -e "${BEFORE}^{commit}" 2>/dev/null; then
  echo "비교 기준 커밋이 없어(첫 push 또는 강제 push) 모든 대상에 배포합니다."
  files="__all__"
else
  files="$(git diff --name-only "$BEFORE" "${GITHUB_SHA:-HEAD}")"
fi

echo "변경 파일:"; echo "$files" | sed 's/^/  /'

has() { [ "$files" = "__all__" ] || grep -qE "$1" <<< "$files"; }
bool() { if "$@"; then echo true; else echo false; fi; }

fe=$(bool has '^frontend/')
be=$(bool has '^(backend/|requirements\.txt$)')
rp=$(bool has '^(rpa/|requirements\.txt$)')
compose=$(bool has '^docker-compose\.yml$')
dep=$(bool has '^deploy/')
ntl=$(bool has '^(frontend/|netlify\.toml$)')
# Render: frontend/ → Static Site, backend/·requirements.txt → Web Service(backend/Dockerfile). 루트 Dockerfile은 전환·롤백용 통합 이미지
rnd=$(bool has '^(backend/|frontend/|Dockerfile$|render\.yaml$|\.dockerignore$|requirements\.txt$)')
all=$([ "$files" = "__all__" ] || [ "$compose" = true ] && echo true || echo false)

services=""
if [ "$EC2_MODE" = "rpa-only" ]; then
  ec2=$([ "$rp" = true ] || [ "$compose" = true ] && echo true || echo false)
  web=false
else
  ec2=$([ "$fe" = true ] || [ "$be" = true ] || [ "$rp" = true ] || [ "$compose" = true ] || [ "$dep" = true ] && echo true || echo false)
  [ "$be" = true ] && services="api"
  [ "$rp" = true ] && services="${services:+$services }rpa"
  # React 화면은 web 이미지(nginx)에 빌드되어 들어가므로 frontend/·deploy/가 바뀌면 web을 다시 빌드한다
  { [ "$fe" = true ] || [ "$dep" = true ]; } && services="${services:+$services }web"
  web=false
fi

echo "결과: netlify=$ntl render=$rnd ec2=$ec2 (mode=$EC2_MODE, all=$all, services='$services', web=$web)"
emit netlify "$ntl"
emit render "$rnd"
emit ec2 "$ec2"
emit ec2_all "$all"
emit ec2_services "$services"
emit ec2_web "$web"
