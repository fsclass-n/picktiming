#!/usr/bin/env bash
# AWS EC2(Ubuntu 22.04/24.04) 최초 1회 설정: Docker 설치 → 저장소 클론 → .env 작성 안내
# 사용: curl 등으로 내려받지 말고, 저장소를 확인한 뒤 EC2에서 직접 실행하세요.
#   bash deploy/ec2-setup.sh https://github.com/<조 Organization>/timepick.git
set -euo pipefail

REPO_URL="${1:?저장소 URL을 인자로 주세요}"
APP_DIR="${APP_DIR:-$HOME/timepick}"

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "Docker 설치 완료. 그룹 적용을 위해 재접속 후 다시 실행하세요."
  exit 0
fi

# 메모리 1GB 인스턴스(t2/t3.micro)는 이미지 빌드(npm·pip) 중 메모리가 모자라 멈출 수 있다 → 스왑 2GB(한 번만)
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3000000 ] && ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "스왑 2GB를 추가했습니다."
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env를 만들었습니다. 로컬 .env를 scp로 덮어쓰거나 운영 값(DATABASE_URL, JWT_SECRET, RPA_API_KEY, GEMINI_API_KEY 등)을 채운 뒤 다시 실행하세요."
  echo "운영 TiDB를 Render·로컬과 함께 쓰므로 app.seed는 실행하지 않습니다(--reset은 운영 데이터 삭제)."
  exit 0
fi

docker compose up -d --build
docker compose ps
for i in $(seq 1 30); do curl -fsS http://localhost/health && echo && exit 0; sleep 3; done
echo "헬스 체크 실패: docker compose logs --tail 50 api 로 원인을 확인하세요."; exit 1
