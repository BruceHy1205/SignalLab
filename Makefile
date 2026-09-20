# 常用命令(开发 / 生产 compose;Windows 见 docs/deploy-windows.md)

.PHONY: db-up db-down migrate dev web test lint sync-instruments sync-csi300 sync-sample \
	dump-qlib prod-config prod-up prod-down prod-backup win-prod-config

COMPOSE = docker compose -f deploy/docker-compose.dev.yml
COMPOSE_PROD = docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod
COMPOSE_WIN = docker compose -f deploy/docker-compose.prod.yml \
	-f deploy/docker-compose.windows.yml --env-file .env.prod
export DATABASE_URL ?= postgresql+psycopg://signal:signal@localhost:5432/signal

db-up:  ## 起 TimescaleDB 并等待就绪,然后跑迁移
	$(COMPOSE) up -d --wait db
	$(MAKE) migrate

db-down:
	$(COMPOSE) down

migrate:
	cd apps/api && uv run alembic upgrade head

dev:  ## 启动 API(热重载)
	cd apps/api && uv run uvicorn signal_api.main:app --reload --port 8000

web:  ## 启动前端(需先 npm install)
	cd apps/web && npm run dev

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

sync-instruments:
	uv run python -m signal_datahub.cli sync-instruments

sync-sample:
	uv run python -m signal_datahub.cli sync-bars --symbols 600519 --days 30 --no-incremental

sync-csi300:
	uv run python -m signal_datahub.cli sync-bars --days 1100

dump-qlib:  ## 导出 Qlib dump_bin 快照到 RESEARCH_DATA_SNAPSHOTS_DIR
	uv run python -m signal_datahub.cli dump-qlib --csi300

prod-config:  ## 校验生产 compose(需 .env.prod 与 docker)
	$(COMPOSE_PROD) config >/dev/null
	@echo "compose.prod OK"

prod-up:  ## 构建并启动生产栈(见 docs/deploy.md)
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

prod-backup:  ## 跑一轮备份(需 --profile backup 服务或已构建 backup 镜像)
	$(COMPOSE_PROD) --profile backup run --rm backup /bin/sh /backup/backup_db.sh

win-prod-config:  ## 校验 Windows 覆盖 compose(需 .env.prod 与 docker)
	$(COMPOSE_WIN) config >/dev/null
	@echo "compose.windows OK"
