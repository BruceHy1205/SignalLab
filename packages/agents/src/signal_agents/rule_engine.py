"""规则决策引擎(无 LLM 时的完整可测路径;有 LLM 时作为兜底)。

角色发言结构与 LLM 路径一致,便于前端统一回放。
"""

from __future__ import annotations

from signal_agents.candidates import CandidateSnapshot, momentum_score


def decide_rule(snap: CandidateSnapshot, position_qty: int = 0) -> dict:
    """返回 {action, confidence, suggested_qty, reason}。"""
    score = momentum_score(snap)
    tech = _tech_view(snap, score)
    fund = _rec_view(snap)
    bull = _bull_view(snap, score)
    bear = _bear_view(snap, score)
    trader = _trader_view(score, position_qty)
    risk = _risk_view(snap, trader["action"])

    # 风控可否决买入
    action = trader["action"]
    if risk.get("veto_buy") and action == "buy":
        action = "hold"
    if risk.get("force_sell") and position_qty > 0:
        action = "sell"

    conf = abs(score)
    qty = 0
    if action == "buy":
        qty = 100
    elif action == "sell" and position_qty > 0:
        qty = position_qty

    return {
        "action": action,
        "confidence": round(conf, 3),
        "suggested_qty": qty,
        "reason": {
            "technical_analyst": tech,
            "recommendation_analyst": fund,
            "bull_researcher": bull,
            "bear_researcher": bear,
            "trader": trader,
            "risk_manager": risk,
            "summary": f"score={score:.3f} → {action}",
            "mode": "rule",
        },
    }


def _tech_view(snap: CandidateSnapshot, score: float) -> str:
    parts = [f"收盘 {snap.close:.2f}"]
    if snap.ret_5d is not None:
        parts.append(f"5日收益 {snap.ret_5d:.2%}")
    if snap.ret_20d is not None:
        parts.append(f"20日收益 {snap.ret_20d:.2%}")
    if snap.ma20 is not None:
        parts.append(f"MA20 {snap.ma20:.2f}({'上方' if snap.above_ma20 else '下方'})")
    parts.append(f"动量分 {score:.2f}")
    return "; ".join(parts)


def _rec_view(snap: CandidateSnapshot) -> str:
    s = snap.rec_stats
    if not s or not s.get("n"):
        return "近期无机构明确推荐记录"
    return (
        f"近窗推荐 {s.get('n')} 次,胜率 {s.get('win_rate')}, "
        f"平均超额 {s.get('avg_excess')},来源 {s.get('sources')}"
    )


def _bull_view(snap: CandidateSnapshot, score: float) -> str:
    if score >= 0:
        return f"短期动量偏强(score={score:.2f}),可考虑逢低配置"
    return f"动能不足(score={score:.2f}),多头论据较弱"


def _bear_view(snap: CandidateSnapshot, score: float) -> str:
    if score < 0:
        return f"跌破均线或机构胜率偏低(score={score:.2f}),宜观望或减仓"
    return f"上行风险可控,但仍需警惕回撤(score={score:.2f})"


def _trader_view(score: float, position_qty: int) -> dict:
    if score >= 0.25:
        return {"action": "buy", "note": "动量与机构信号偏多,建议买入"}
    if score <= -0.25 and position_qty > 0:
        return {"action": "sell", "note": "动能转弱且有持仓,建议卖出"}
    return {"action": "hold", "note": "信号不明确,保持观望"}


def _risk_view(snap: CandidateSnapshot, action: str) -> dict:
    veto = False
    force = False
    note = "风险可控"
    if snap.ret_5d is not None and snap.ret_5d < -0.08 and action == "buy":
        veto = True
        note = "近5日跌幅过大,否决追高买入"
    if snap.ret_5d is not None and snap.ret_5d < -0.12:
        force = True
        note = "急跌风控:建议减仓"
    return {"veto_buy": veto, "force_sell": force, "note": note}
