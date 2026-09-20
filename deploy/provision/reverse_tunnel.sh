#!/usr/bin/env bash
# 开发期回调可达性:在内网开发环境时,从远端建立到本机 API 的反向隧道。
# 在**本机(主程序侧)**执行,保持前台或用 systemd/tmux 托管:
#   bash reverse_tunnel.sh --host 1.2.3.4 --user ubuntu \
#     --remote-port 18000 --local-port 8000 [--key ~/.ssh/id_ed25519]
#
# 任务 callback 应设为 http://127.0.0.1:18000 (远端视角) 或经隧道可达地址。
# 本脚本不传输任何 LLM/HMAC secret。
set -euo pipefail

HOST=""
USER_NAME="ubuntu"
REMOTE_PORT=18000
LOCAL_PORT=8000
KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --remote-port) REMOTE_PORT="$2"; shift 2 ;;
    --local-port) LOCAL_PORT="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 --host IP --user ubuntu [--remote-port 18000] [--local-port 8000] [--key PATH]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "--host required" >&2
  exit 2
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -N -R "${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}")
if [[ -n "$KEY" ]]; then
  SSH_OPTS+=(-i "$KEY")
fi

echo "[tunnel] ${USER_NAME}@${HOST} remote:${REMOTE_PORT} -> local:${LOCAL_PORT}"
exec ssh "${SSH_OPTS[@]}" "${USER_NAME}@${HOST}"
