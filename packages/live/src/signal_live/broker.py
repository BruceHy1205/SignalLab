"""Broker 端口与实现。

miniqmt 依赖 Windows + 券商 QMT 客户端 + xtquant,主平台默认不安装。
未安装时 MiniqmtBroker 给出明确错误;开发/CI 用 StubBroker。

真机注意:xtquant 只能连本机已登录的 miniQMT,不能放进 Linux 容器。
Windows 上推荐 Docker 跑 db/web/caddy,API 用 host 进程 + LIVE_BROKER=miniqmt。
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerSubmitResult:
    broker_order_id: str
    status: str  # submitted / rejected
    message: str = ""


class BrokerPort(Protocol):
    name: str

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> BrokerSubmitResult: ...


class StubBroker:
    """本地/测试用:不连真通道,直接返回假单号。"""

    name = "stub"

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> BrokerSubmitResult:
        oid = f"stub-{uuid.uuid4().hex[:12]}"
        logger.info(
            "StubBroker submit %s %s %s @%s -> %s",
            side,
            quantity,
            symbol,
            limit_price,
            oid,
        )
        return BrokerSubmitResult(broker_order_id=oid, status="submitted", message="stub ok")


def _to_qmt_code(symbol: str) -> str:
    """主平台 600519.SH → QMT 常用 600519.SH(已规范则原样)。"""
    s = (symbol or "").strip().upper()
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("5", "6", "9")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


class MiniqmtBroker:
    """miniQMT / xtquant 适配(可选依赖)。

    需要环境:
    - Windows + 已登录的 miniQMT
    - `xtquant` 可 import(通常随券商 QMT 安装)
    - LIVE_MINIQMT_ACCOUNT 资金账号
    - LIVE_MINIQMT_PATH 指向 userdata_mini 目录
    """

    name = "miniqmt"

    def __init__(
        self,
        account: str = "",
        path: str = "",
        *,
        session_id: int | None = None,
        account_type: str = "STOCK",
    ) -> None:
        self._account = (account or os.environ.get("LIVE_MINIQMT_ACCOUNT") or "").strip()
        self._path = (path or os.environ.get("LIVE_MINIQMT_PATH") or "").strip()
        self._session_id = session_id
        self._account_type = account_type or "STOCK"
        self._trader: Any | None = None
        self._acc: Any | None = None
        self._lock = threading.Lock()

    def probe(self) -> dict[str, Any]:
        """连通性检查(不下单)。供 CLI / 健康页使用。"""
        info: dict[str, Any] = {
            "broker": self.name,
            "account_configured": bool(self._account),
            "path": self._path or None,
            "path_exists": bool(self._path and os.path.isdir(self._path)),
            "xtquant_importable": False,
            "connected": False,
            "message": "",
        }
        try:
            import xtquant  # type: ignore[import-not-found]  # noqa: F401

            info["xtquant_importable"] = True
        except ImportError:
            info["message"] = "未安装 xtquant;请在已装 miniQMT 的 Windows 上运行 host API"
            return info
        if not self._account:
            info["message"] = "LIVE_MINIQMT_ACCOUNT 未配置"
            return info
        if not self._path:
            info["message"] = "LIVE_MINIQMT_PATH 未配置(应指向 userdata_mini)"
            return info
        if not info["path_exists"]:
            info["message"] = f"路径不存在: {self._path}"
            return info
        try:
            self._ensure_connected()
            info["connected"] = True
            info["message"] = "ok"
        except Exception as e:
            info["message"] = str(e)[:300]
        return info

    def _ensure_connected(self) -> tuple[Any, Any]:
        with self._lock:
            if self._trader is not None and self._acc is not None:
                return self._trader, self._acc
            try:
                from xtquant import xttrader  # type: ignore[import-not-found]
                from xtquant.xttype import StockAccount  # type: ignore[import-not-found]
            except ImportError:
                from xtquant import xttrader  # type: ignore[import-not-found]

                StockAccount = xttrader.StockAccount  # type: ignore[attr-defined]

            if not self._account:
                raise RuntimeError("LIVE_MINIQMT_ACCOUNT 未配置")
            if not self._path:
                raise RuntimeError(
                    "LIVE_MINIQMT_PATH 未配置;应指向 miniQMT 安装目录下的 userdata_mini"
                )
            if not os.path.isdir(self._path):
                raise RuntimeError(f"LIVE_MINIQMT_PATH 不存在: {self._path}")

            session_id = self._session_id
            if session_id is None:
                raw = os.environ.get("LIVE_MINIQMT_SESSION_ID")
                session_id = int(raw) if raw else int(time.time()) % 1_000_000_000
            trader = xttrader.XtQuantTrader(self._path, int(session_id))
            trader.start()
            connect_result = trader.connect()
            if connect_result != 0:
                raise RuntimeError(
                    f"miniQMT connect 失败 code={connect_result};"
                    "请确认客户端已登录且 userdata_mini 路径正确"
                )
            try:
                acc = StockAccount(self._account, self._account_type)
            except TypeError:
                acc = StockAccount(self._account)
            sub = trader.subscribe(acc)
            if sub is not None and sub != 0:
                logger.warning("miniQMT subscribe 返回 %s(继续尝试下单)", sub)
            self._trader = trader
            self._acc = acc
            logger.info("MiniqmtBroker connected account=%s path=%s", self._account, self._path)
            return trader, acc

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> BrokerSubmitResult:
        try:
            from xtquant import xtconstant  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "未安装 xtquant/miniQMT。请在已登录 miniQMT 的 Windows 环境用 host API 运行,"
                "或将 LIVE_BROKER=stub 做联调。Linux Docker 容器内无法直连 miniQMT。"
            ) from e

        if quantity <= 0 or quantity % 100 != 0:
            raise RuntimeError(f"A 股数量须为 100 的整数倍,收到 {quantity}")

        trader, acc = self._ensure_connected()
        code = _to_qmt_code(symbol)
        side_l = side.lower().strip()
        order_type = xtconstant.STOCK_BUY if side_l == "buy" else xtconstant.STOCK_SELL
        if limit_price is not None:
            price_type = xtconstant.FIX_PRICE
            price = float(limit_price)
        else:
            price_type = xtconstant.LATEST_PRICE
            price = 0.0

        try:
            order_id = trader.order_stock(
                acc,
                code,
                order_type,
                int(quantity),
                price_type,
                price,
                "signal",
                "live",
            )
            if order_id is None or int(order_id) < 0:
                return BrokerSubmitResult(
                    broker_order_id=str(order_id),
                    status="rejected",
                    message=f"miniqmt rejected: {order_id}",
                )
            return BrokerSubmitResult(
                broker_order_id=str(order_id),
                status="submitted",
                message="miniqmt ok",
            )
        except Exception as e:
            # 连接可能已断,下次重建
            with self._lock:
                self._trader = None
                self._acc = None
            raise RuntimeError(f"miniqmt 下单失败: {e}") from e


def build_broker(kind: str, *, account: str = "", path: str = "") -> BrokerPort:
    k = (kind or "stub").strip().lower()
    if k in ("stub", "fake", "mock"):
        return StubBroker()
    if k in ("miniqmt", "qmt", "xtquant"):
        return MiniqmtBroker(account=account, path=path)
    raise ValueError(f"未知 LIVE_BROKER: {kind!r}(支持 stub|miniqmt)")
