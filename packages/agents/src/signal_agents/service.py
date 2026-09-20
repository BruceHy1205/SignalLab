"""Agent 决策服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from signal_agents import repo
from signal_agents.candidates import build_candidate_pool, snapshot_symbol
from signal_agents.ports import MarketPort, PaperPort, TrackerPort, WatchlistPort
from signal_agents.rule_engine import decide_rule

logger = logging.getLogger(__name__)


@dataclass
class AgentSettings:
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    max_candidates: int = 10
    max_llm_cost_usd: float = 2.0
    # 粗略:每只股票 LLM 路径约 $0.02(可调)
    cost_per_symbol_usd: float = 0.02


class AgentService:
    def __init__(
        self,
        market: MarketPort,
        tracker: TrackerPort,
        paper: PaperPort,
        watchlist: WatchlistPort,
        settings: AgentSettings | None = None,
    ) -> None:
        self._market = market
        self._tracker = tracker
        self._paper = paper
        self._watchlist = watchlist
        self._settings = settings or AgentSettings()

    def run(
        self,
        session: Session,
        *,
        account_id: str | None = None,
        extra_symbols: list[str] | None = None,
        force_rule: bool = False,
    ) -> dict:
        symbols = build_candidate_pool(
            self._watchlist,
            self._tracker,
            extra=extra_symbols,
            limit=self._settings.max_candidates,
        )
        use_llm = bool(self._settings.llm_api_key) and not force_rule
        model = self._settings.llm_model if use_llm else "rule"
        run = repo.create_run(session, model=model, candidate_count=len(symbols))
        session.commit()

        positions = {
            p["symbol"]: p["quantity"]
            for p in (self._paper.list_positions(account_id) if account_id else [])
        }
        cost = 0.0
        created = 0
        try:
            for symbol in symbols:
                if (
                    use_llm
                    and cost + self._settings.cost_per_symbol_usd > self._settings.max_llm_cost_usd
                ):
                    logger.warning("达到 LLM 预算上限,后续改用规则")
                    use_llm = False
                snap = snapshot_symbol(self._market, self._tracker, symbol)
                if snap is None:
                    continue
                pos_qty = int(positions.get(symbol, 0))
                if use_llm:
                    try:
                        from signal_agents.llm_engine import decide_llm

                        decision = decide_llm(
                            snap,
                            pos_qty,
                            api_key=self._settings.llm_api_key,
                            base_url=self._settings.llm_base_url,
                            model=self._settings.llm_model,
                        )
                        cost += self._settings.cost_per_symbol_usd
                    except Exception:
                        logger.exception("LLM 决策失败 %s,回退规则", symbol)
                        decision = decide_rule(snap, pos_qty)
                else:
                    decision = decide_rule(snap, pos_qty)

                repo.insert_signal(
                    session,
                    run_id=run.id,
                    symbol=symbol,
                    action=decision["action"],
                    confidence=float(decision["confidence"]),
                    suggested_qty=int(decision["suggested_qty"]),
                    reason=decision["reason"],
                )
                created += 1
            repo.finish_run(session, run, "succeeded", llm_cost_usd=cost)
            session.commit()
        except Exception as e:
            session.rollback()
            run = repo.get_run(session, run.id) or run
            repo.finish_run(session, run, "failed", llm_cost_usd=cost, error=str(e)[:500])
            session.commit()
            raise

        return {
            "run_id": run.id,
            "status": "succeeded",
            "signals": created,
            "candidates": len(symbols),
            "model": model,
            "llm_cost_usd": cost,
        }

    def adopt_signal(
        self, session: Session, signal_id: str, account_id: str, quantity: int | None = None
    ) -> dict:
        """把信号变成模拟盘订单。"""
        sig = repo.get_signal(session, signal_id)
        if not sig:
            raise KeyError(signal_id)
        if sig.action == "hold":
            raise ValueError("hold 信号无需下单")
        qty = quantity if quantity is not None else sig.suggested_qty
        if qty <= 0:
            raise ValueError("数量无效")
        return self._paper.place_order(
            account_id,
            sig.symbol,
            sig.action,
            qty,
            note=f"adopt signal {sig.id}",
        )
