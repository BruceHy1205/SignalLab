# SignalLab — 投资研究平台

以 Agent 自动化平台为核心的投资研究软件：机构推荐胜率追踪、模拟盘、多智能体决策、自动化量化策略研发。

- 产品说明：[docs/analysis.md](docs/analysis.md)
- 架构设计：[docs/architecture.md](docs/architecture.md)
- 生产部署：[docs/deploy.md](docs/deploy.md)

## 快速开始（开发机）

生产 / Windows 见 `docs/deploy.md` 与 `docs/deploy-windows.md`。

前置：[uv](https://docs.astral.sh/uv/)、Docker Desktop、Node.js 20+。

```bash
# 1. 安装依赖
uv sync --all-packages
cd apps/web && npm install && cd ../..

# 2. 起数据库 (TimescaleDB) 并完成迁移
make db-up

# 3. 启动 API + 前端 (两个终端)
make dev          # http://localhost:8000
make web          # http://localhost:3000

# 4. 同步数据 (需本机可访问东财/深交所)
make sync-sample
make sync-instruments
make sync-csi300

# 5. 浏览器打开 http://localhost:3000/import 导入聊天记录
#    查看推荐 http://localhost:3000 、机构排行 /leaderboard
```

- `make test` 不依赖外网行情源。
- 配置 `.env` 中 `LLM_API_KEY` 后 tracker 用 DeepSeek 结构化抽取；未配置则走规则粗抽（热门股关键词）。

## 仓库结构

```
apps/api           FastAPI 组装层 (唯一允许 import 所有业务包的地方)
apps/web           Next.js 前端 (推荐追踪 / 机构排行 / 导入)
packages/contracts 三份契约：策略包 / 研究任务规格 / runner 回报协议
packages/datahub   行情数据服务 (AKShare 主 / Tushare 备)
packages/tracker   机构推荐胜率追踪 (解析/抽取/消歧/event study)
packages/papertrade 模拟盘 (次日开盘撮合、日终结算、净值)
packages/agents    多智能体决策 (LangGraph + 规则兜底)
packages/research  研究任务管理 (job/供给器/策略包校验)
packages/notify    通知 (邮件 SMTP + 飞书 webhook)
packages/live      实盘意图队列 (人工确认; stub/miniqmt)
deploy/            docker compose 与远端 runner 供给脚本
runners/           研究执行环境 (AlphaAgent/RD-Agent stub|real + reporter, 独立依赖树)
deploy/provision/  远端 runner 主机一键供给与反向隧道
docs/              产品说明、架构与部署文档
```

架构守护：业务包之间禁止互相 import（只共享 contracts），由 import-linter 在 CI 强制。tracker 通过 BarsReader 端口读行情，不直接依赖 datahub。

研究任务：浏览器打开 http://localhost:3000/research 。支持双框架——AlphaAgent 本地/远程、RD-Agent 远程（建议 Linux x86）；`RESEARCH_RUNNER_BACKEND=stub|real`。心跳/策略包经 HMAC 回报，失联时 SSH 拉回 `events.jsonl` 补账，结束后清理远端工作目录。

## 生产 (Linux 云主机)

见 [docs/deploy.md](docs/deploy.md)。摘要：

```bash
cp .env.prod.example .env.prod   # 修改密码与 Caddy Basic Auth 哈希
make prod-up                     # db + api + web + caddy
make prod-backup                 # 可选每日备份 profile
```

## 开发

```bash
make test   # 单元测试
make lint   # ruff + import-linter
```
