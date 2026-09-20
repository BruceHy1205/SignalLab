# 生产部署

目标:Linux 裸机/云主机 → 全服务可用(API + Web + TimescaleDB + Caddy),可选每日备份。

与开发环境的差异只在 `.env`;业务代码同一份 compose 构建。

**Windows 主机**(Docker Desktop + 可选真 miniQMT)见 [`docs/deploy-windows.md`](./deploy-windows.md)。

## 前置

- Docker Engine 24+ 与 Docker Compose v2
- 开放 80/443(若用域名 HTTPS)
- (可选)域名已解析到主机

## ≤30 分钟上手

```bash
git clone <repo> signal && cd signal

# 1. 环境文件
cp .env.prod.example .env.prod
# 必改: POSTGRES_PASSWORD / RUNNER_CALLBACK_SECRET / Caddy 密码哈希
# 生成密码哈希:
docker run --rm caddy:2-alpine caddy hash-password --plaintext '你的密码'
# 把输出写入 CADDY_BASIC_AUTH_HASH,每个 $ 写成 $$

# 有公网域名时:
# SIGNAL_SITE_ADDRESS=your.domain.com
# CADDY_ACME_EMAIL=you@example.com

# 2. 构建并启动
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d --build

# 3. 检查
curl -u admin:你的密码 http://127.0.0.1/health
# 浏览器打开 http://<主机>/  (Basic Auth 弹窗)
```

可选每日备份(本地卷 + 可选 S3):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod --profile backup up -d
```

## 服务拓扑

| 服务 | 说明 |
|------|------|
| `db` | TimescaleDB(pg16),数据卷 `dbdata` |
| `api` | FastAPI;启动时 `alembic upgrade head` |
| `web` | Next.js standalone |
| `caddy` | 反代 + Basic Auth + 可选 HTTPS |
| `backup` | profile;周期 `pg_dump` → gzip,可选 `aws s3 cp` |

Caddy 路由:`/api/*` `/health` `/docs*` → api;`/` → web。

## 备份与恢复演练

手动备份(在已运行的 compose 网络内):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod run --rm backup \
  /bin/sh /backup/backup_db.sh
```

恢复演练(建议在临时库或停写窗口):

```bash
# 将 backup_data 卷中的某份 .sql.gz 拷出,或:
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod run --rm \
  -v signal-prod_backup_data:/var/backups/signal backup \
  /bin/sh /backup/restore_db.sh /var/backups/signal/signal-XXXX.sql.gz
```

恢复后重启 api,核对 `/health` 与关键页面。

## 定时任务时区

`SCHEDULER_TIMEZONE=Asia/Shanghai`(默认),日终增量/研究探活等与开发期一致。云主机系统时区可保持 UTC,由 APScheduler 按时区触发。

## 与开发环境关系

| | 开发 | 生产(Linux) | 生产(Windows) |
|--|------|-------------|----------------|
| DB | `deploy/docker-compose.dev.yml` 只起库 | compose.prod 内 `db` | 同左 + `windows.yml` |
| API/Web | `make dev` / `make web` | 容器 | 全容器;或 API 宿主机(真 miniQMT) |
| 入口 | localhost:3000/8000 | Caddy :80/:443 | 同左;端口冲突可改 `CADDY_HTTP_PORT` |

## 常见问题

- **Basic Auth 401**:检查哈希里 `$` 是否写成 `$$`;用户名是否匹配。
- **API 连不上 DB**:等 healthcheck;核对 `POSTGRES_*` 与 `DATABASE_URL` 一致(compose 已自动拼)。
- **研究回调**:runner 在公网时把 `RESEARCH_CALLBACK_HOST` 设为 `https://your.domain.com`。
- **不要**在镜像里 `pip install` qlib/rdagent;研究任务仍走 runners / remote_ssh。
- **真 miniQMT**:容器内 `LIVE_BROKER=miniqmt` 无效,见 `docs/deploy-windows.md` 模式 B。
