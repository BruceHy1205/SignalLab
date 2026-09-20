"""可选 LLM 路径:LangGraph 顺序角色辩论。

失败或未配置时由调用方回退 rule_engine。
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from signal_agents.candidates import CandidateSnapshot
from signal_agents.rule_engine import decide_rule

logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    snap: CandidateSnapshot
    position_qty: int
    technical: str
    recommendation: str
    bull: str
    bear: str
    trader_action: str
    trader_note: str
    risk_note: str
    veto_buy: bool
    force_sell: bool
    final: dict


def _llm(api_key: str, base_url: str, model: str) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=api_key,  # type: ignore[arg-type]
        base_url=base_url,
        model=model,
        temperature=0.2,
    )


def _ask(llm: ChatOpenAI, system: str, user: str) -> str:
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return str(resp.content)


def build_graph(llm: ChatOpenAI):
    def ctx(snap: CandidateSnapshot, position_qty: int) -> str:
        return (
            f"股票 {snap.symbol} 收盘 {snap.close}\n"
            f"5日收益 {snap.ret_5d} 20日收益 {snap.ret_20d}\n"
            f"MA5 {snap.ma5} MA20 {snap.ma20} 站上MA20 {snap.above_ma20}\n"
            f"机构统计 {json.dumps(snap.rec_stats, ensure_ascii=False)}\n"
            f"当前持仓股数 {position_qty}"
        )

    def technical(state: GraphState) -> dict:
        text = _ask(
            llm,
            "你是技术分析师,用中文简洁给出观点(不超过80字)。",
            ctx(state["snap"], state["position_qty"]),
        )
        return {"technical": text}

    def recommendation(state: GraphState) -> dict:
        text = _ask(
            llm,
            "你是机构推荐分析师,结合机构胜率数据用中文给出观点(不超过80字)。",
            ctx(state["snap"], state["position_qty"]) + f"\n技术面:{state['technical']}",
        )
        return {"recommendation": text}

    def bull(state: GraphState) -> dict:
        text = _ask(
            llm,
            "你是多头研究员,给出看多论据(不超过60字)。",
            f"技术:{state['technical']}\n机构:{state['recommendation']}",
        )
        return {"bull": text}

    def bear(state: GraphState) -> dict:
        text = _ask(
            llm,
            "你是空头研究员,给出看空/谨慎论据(不超过60字)。",
            f"技术:{state['technical']}\n机构:{state['recommendation']}",
        )
        return {"bear": text}

    def trader(state: GraphState) -> dict:
        raw = _ask(
            llm,
            '你是交易员。只输出 JSON:{"action":"buy|sell|hold","note":"...","confidence":0-1}',
            f"多头:{state['bull']}\n空头:{state['bear']}\n持仓:{state['position_qty']}",
        )
        try:
            start, end = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            action = data.get("action", "hold")
            if action not in ("buy", "sell", "hold"):
                action = "hold"
            return {
                "trader_action": action,
                "trader_note": str(data.get("note", "")),
                "final": {"confidence": float(data.get("confidence", 0.5))},
            }
        except Exception:
            fallback = decide_rule(state["snap"], state["position_qty"])
            return {
                "trader_action": fallback["action"],
                "trader_note": "LLM解析失败,回退规则",
                "final": {"confidence": fallback["confidence"]},
            }

    def risk(state: GraphState) -> dict:
        raw = _ask(
            llm,
            '你是风控。只输出 JSON:{"veto_buy":bool,"force_sell":bool,"note":"..."}',
            f"拟操作:{state['trader_action']}\n{ctx(state['snap'], state['position_qty'])}",
        )
        try:
            start, end = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            veto = bool(data.get("veto_buy", False))
            force = bool(data.get("force_sell", False))
            note = str(data.get("note", ""))
        except Exception:
            veto, force, note = False, False, "风控解析失败,放行"
        action = state["trader_action"]
        if veto and action == "buy":
            action = "hold"
        if force and state["position_qty"] > 0:
            action = "sell"
        # 无持仓时不允许 sell(与规则引擎一致)
        if action == "sell" and state["position_qty"] <= 0:
            action = "hold"
        qty = 100 if action == "buy" else (state["position_qty"] if action == "sell" else 0)
        conf = float(state.get("final", {}).get("confidence", 0.5))
        return {
            "veto_buy": veto,
            "force_sell": force,
            "risk_note": note,
            "final": {
                "action": action,
                "confidence": conf,
                "suggested_qty": qty,
                "reason": {
                    "technical_analyst": state["technical"],
                    "recommendation_analyst": state["recommendation"],
                    "bull_researcher": state["bull"],
                    "bear_researcher": state["bear"],
                    "trader": {"action": state["trader_action"], "note": state["trader_note"]},
                    "risk_manager": {
                        "veto_buy": veto,
                        "force_sell": force,
                        "note": note,
                    },
                    "summary": f"LLM → {action}",
                    "mode": "llm",
                },
            },
        }

    g = StateGraph(GraphState)
    g.add_node("technical", technical)
    g.add_node("recommendation", recommendation)
    g.add_node("bull", bull)
    g.add_node("bear", bear)
    g.add_node("trader", trader)
    g.add_node("risk", risk)
    g.set_entry_point("technical")
    g.add_edge("technical", "recommendation")
    g.add_edge("recommendation", "bull")
    g.add_edge("bull", "bear")
    g.add_edge("bear", "trader")
    g.add_edge("trader", "risk")
    g.add_edge("risk", END)
    return g.compile()


def decide_llm(
    snap: CandidateSnapshot,
    position_qty: int,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> dict:
    graph = build_graph(_llm(api_key, base_url, model))
    state: GraphState = {
        "snap": snap,
        "position_qty": position_qty,
        "technical": "",
        "recommendation": "",
        "bull": "",
        "bear": "",
        "trader_action": "hold",
        "trader_note": "",
        "risk_note": "",
        "veto_buy": False,
        "force_sell": False,
        "final": {},
    }
    out = graph.invoke(state)
    final = out.get("final") or decide_rule(snap, position_qty)
    if "action" not in final:
        return decide_rule(snap, position_qty)
    return final
