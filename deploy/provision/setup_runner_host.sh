#!/usr/bin/env bash
# 裸 Ubuntu → Docker 就绪 + 可选拉取 runner 镜像。
# 用法(在远端执行,或不含 secrets 地经 SSH 下发):
#   bash setup_runner_host.sh [--image signal-rdagent:stub] [--mirror]
# 本脚本绝不写入 LLM key / HMAC secret。
set -euo pipefail

IMAGE="${SIGNAL_RUNNER_IMAGE:-signal-rdagent:stub}"
USE_MIRROR=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE="$2"
      shift 2
      ;;
    --mirror)
      USE_MIRROR=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--image NAME] [--mirror]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

export DEBIAN_FRONTEND=noninteractive

if ! command -v docker >/dev/null 2>&1; then
  echo "[provision] installing docker..."
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg rsync
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  fi
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  systemctl enable --now docker || true
else
  echo "[provision] docker already present"
  command -v rsync >/dev/null 2>&1 || apt-get install -y -qq rsync || true
fi

if [[ "$USE_MIRROR" == "1" ]]; then
  mkdir -p /etc/docker
  cat >/etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
EOF
  systemctl restart docker || true
fi

if ! docker info >/dev/null 2>&1; then
  echo "[provision] docker daemon not usable" >&2
  exit 1
fi

echo "[provision] ensuring image: $IMAGE"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker pull "$IMAGE" || {
    echo "[provision] pull failed; build locally if you have the Dockerfile context"
    exit 0
  }
fi

mkdir -p /tmp/signal-jobs
echo "[provision] ready"
