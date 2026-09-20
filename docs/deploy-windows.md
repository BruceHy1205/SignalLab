# Windows 部署(Docker 优先 + 真 miniQMT)

目标主机可从 macOS 等平台迁到 **Windows**。业务镜像与 Linux 共用;`deploy/docker-compose.prod.yml` 为主,
Windows 用覆盖文件补端口/`host.docker.internal`/live 环境变量。

## 架构选择

| 模式 | 适用 | 命令 |
|------|------|------|
| **A. 全 Docker** | 日常使用、模拟盘、研究调度;`LIVE_BROKER=stub` | `deploy/windows/up.ps1` |
| **B. Docker + host API** | **真 miniQMT 下单** | `up.ps1 -Miniqmt` + `run-host-api.ps1` |

原因:xtquant 只能连本机已登录的 miniQMT,**不能**放进 Linux 容器。

```
模式 A:
  [Caddy] → [api 容器 stub] → [db]
         → [web]

模式 B:
  [Caddy] → host.docker.internal:8000 (Windows 上的 API + xtquant)
         → [web]
  [db] ← API 经 localhost:5432
  [miniQMT 客户端已登录]
```

## 前置

1. [Docker Desktop](https://www.docker.com/products/docker-desktop/)(WSL2 后端)
2. Git + (模式 B) [uv](https://github.com/astral-sh/uv) + Python 3.11/3.12
3. 模式 B:券商 **miniQMT** 已安装并登录;记下 `userdata_mini` 路径与资金账号

## ≤30 分钟:模式 A(全 Docker)

在仓库根目录 PowerShell:

```powershell
copy .env.prod.example .env.prod
# 编辑 .env.prod: POSTGRES_PASSWORD / RUNNER_CALLBACK_SECRET / Caddy 密码
# 生成哈希:
docker run --rm caddy:2-alpine caddy hash-password --plaintext "你的密码"
# 写入 CADDY_BASIC_AUTH_HASH,每个 $ 写成 $$
# 若 80 端口被占: CADDY_HTTP_PORT=8080

powershell -ExecutionPolicy Bypass -File deploy/windows/up.ps1
powershell -ExecutionPolicy Bypass -File deploy/windows/check.ps1
```

浏览器打开 `http://127.0.0.1/`(或 `:8080`),Basic Auth 登录。

等价手动命令:

```powershell
docker compose `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.windows.yml `
  --env-file .env.prod up -d --build
```

## 模式 B:真 miniQMT

### 1. `.env.prod` 增加

```env
LIVE_BROKER=miniqmt
LIVE_MINIQMT_ACCOUNT=你的资金账号
LIVE_MINIQMT_PATH=D:\某券商QMT交易端\userdata_mini
POSTGRES_HOST_PORT=5432
HOST_API_PORT=8000
```

路径必须是 **`userdata_mini` 目录**,不是 QMT 安装根目录。

### 2. 起 DB / Web / Caddy

```powershell
powershell -ExecutionPolicy Bypass -File deploy/windows/up.ps1 -Miniqmt
```

### 3. 宿主机跑 API

另开 PowerShell(保持 QMT 登录):

```powershell
# 建议用券商自带 Python 或已能 import xtquant 的环境
uv sync --all-packages
powershell -ExecutionPolicy Bypass -File deploy/windows/run-host-api.ps1
```

脚本会先 `python -m signal_live.probe`,再 migrate + uvicorn。

### 4. 验证

```powershell
powershell -ExecutionPolicy Bypass -File deploy/windows/check.ps1 -Miniqmt
# 或
curl http://127.0.0.1:8000/api/live/broker
```

前端 `/live` 创建意图 → **确认** 后才会真下单。

## 研究任务(Windows 主机)

- 主平台可全在 Windows Docker 跑。
- **RD-Agent** 仍建议另开 Linux x86(本机 WSL2 Ubuntu 或局域网 Linux x86 主机)做 `remote_ssh`。
- AlphaAgent stub 可本机;real 需在 runner 环境安装。

## 常见问题

| 现象 | 处理 |
|------|------|
| 80 端口占用 | `.env.prod` 设 `CADDY_HTTP_PORT=8080` |
| `connect 失败` | QMT 是否登录;`LIVE_MINIQMT_PATH` 是否为 `userdata_mini` |
| 有 order_id 无委托 | 资金账号是否与客户端右上角一致 |
| 容器里 `LIVE_BROKER=miniqmt` | **无效**;请改模式 B |
| web 起不来 | 模式 B 已去掉对 api 容器的 depends_on;确认只用了 `windows-miniqmt` 覆盖文件 |
| Basic Auth 401 | 哈希里 `$` → `$$` |

## 与其他开发环境的关系

同一份 compose 与业务代码。亦可继续在其他系统上 `make db-up` / `make dev` 亦可;
生产主路径可切到 Windows Docker,无需单独一台常开开发机。
