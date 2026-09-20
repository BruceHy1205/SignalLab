# runners/

研究执行环境 (RD-Agent / AlphaAgent) 与数据导出，**独立于主平台依赖树**。

主平台 Python 环境永远不安装 qlib / rdagent / alphaagent。

## 双框架怎么选

| 框架 | 擅长 | 推荐环境 | 默认供给 |
|------|------|----------|----------|
| **AlphaAgent** | 可解释因子挖掘、本地 `USE_LOCAL` | 与主平台同机或任意 Linux | `local` / 可选 `remote_ssh` |
| **RD-Agent** | `fin_factor` 闭环、官方 Linux/amd64 | Linux x86 主机 / 云服务器 | `remote_ssh` |

推荐拓扑：

1. **主开发工作站**：跑主平台 + **AlphaAgent**（stub 或 real 本地）
2. **Linux x86 服务器**（Ubuntu / WSL2 / 云主机）：预构建 `signal-rdagent:*` 镜像，作为 **RD-Agent remote_ssh** 节点

## 后端开关

- `SIGNAL_RUNNER_BACKEND=stub`（默认）：冒烟假跑，CI/本机无需安装重依赖
- `SIGNAL_RUNNER_BACKEND=real`：调用官方 CLI（`alphaagent mine` / `rdagent fin_factor`）
  - 可用 `SIGNAL_ALPHAAGENT_CMD` / `SIGNAL_RDAGENT_CMD` 覆盖整条命令
  - 真实产出优先读工作目录 `result.json`（含 `factors[].expression`）

主平台侧对应环境变量：`RESEARCH_RUNNER_BACKEND`

## 目录

### AlphaAgent

- `runner.py` — 统一入口
- `real_backend.py` — 真实 CLI 适配 + harvest
- `to_package.py` — 中间结果 → 策略包 zip
- `Dockerfile` — `BACKEND=stub|real`

```bash
docker build -t signal-alphaagent:stub -f runners/alphaagent/Dockerfile .
docker build --build-arg BACKEND=real -t signal-alphaagent:real -f runners/alphaagent/Dockerfile .
```

### RD-Agent

- `runner.py` / `real_backend.py` / `to_package.py` / `Dockerfile` 同上

```bash
# 建议在 Linux x86 上构建
docker build -t signal-rdagent:stub -f runners/rdagent/Dockerfile .
docker build --build-arg BACKEND=real -t signal-rdagent:real -f runners/rdagent/Dockerfile .
```

### 公共

- `common/reporter.py` — 心跳/上传/终态 + budget guard
- `common/backend.py` — stub/real 解析

## 数据快照

- 主平台 CLI：`uv run python -m signal_datahub.cli dump-qlib --out-root $RESEARCH_DATA_SNAPSHOTS_DIR --csi300`
- 实现位于 `packages/datahub/qlib_dump.py`（纯 numpy 写 dump_bin，**不安装 qlib**）

## real 镜像注意

Dockerfile 的 real 变体默认只切换 `SIGNAL_RUNNER_BACKEND=real`；
请在目标机自行 `pip install` / 多层构建装入 AlphaAgent 或 RD-Agent，
勿把它们装进主平台 `uv` 环境。
