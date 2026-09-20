# 可选:在容器内跑 dump-qlib(与主平台同一代码,仍不安装 qlib)
# docker build -t signal-data-export -f runners/data_export/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
COPY packages/datahub packages/datahub
COPY packages/contracts packages/contracts
RUN uv sync --frozen --no-dev --no-editable --package signal-datahub
ENV PATH="/app/.venv/bin:$PATH" \
    RESEARCH_DATA_SNAPSHOTS_DIR=/snapshots
VOLUME ["/snapshots"]
ENTRYPOINT ["python", "-m", "signal_datahub.cli", "dump-qlib", "--out-root", "/snapshots"]
