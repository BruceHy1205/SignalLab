"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiGet, apiPost } from "@/lib/api";

type Run = {
  id: string;
  status: string;
  model: string;
  llm_cost_usd: number;
  candidate_count: number;
  started_at: string;
  finished_at: string | null;
  error: string;
};

type SignalSummary = {
  id: string;
  run_id: string;
  symbol: string;
  action: string;
  confidence: number;
  suggested_qty: number;
  summary: string;
  mode: string;
};

type SignalDetail = SignalSummary & {
  reason: Record<string, unknown>;
};

type Account = { id: string; name: string };

const ROLES = [
  ["technical_analyst", "技术分析"],
  ["recommendation_analyst", "机构推荐"],
  ["bull_researcher", "多头"],
  ["bear_researcher", "空头"],
  ["trader", "交易员"],
  ["risk_manager", "风控"],
] as const;

function actionBadgeClass(action: string) {
  const a = action?.toLowerCase();
  if (a === "buy") return "badge badge-buy";
  if (a === "sell") return "badge badge-sell";
  if (a === "hold") return "badge badge-hold";
  return "badge badge-neutral";
}

export default function AgentsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [signals, setSignals] = useState<SignalSummary[]>([]);
  const [active, setActive] = useState<SignalDetail | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [extra, setExtra] = useState("600519.SH");
  const [forceRule, setForceRule] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [r, s, a] = await Promise.all([
      apiGet<Run[]>("/api/agents/runs"),
      apiGet<SignalSummary[]>("/api/agents/signals?limit=50"),
      apiGet<Account[]>("/api/papertrade/accounts"),
    ]);
    setRuns(r);
    setSignals(s);
    setAccounts(a);
    if (!accountId && a[0]) setAccountId(a[0].id);
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
  }, []);

  async function runAgents() {
    setBusy(true);
    setMsg(null);
    try {
      const extras = extra
        .split(/[,\s]+/)
        .map((x) => x.trim())
        .filter(Boolean);
      const result = await apiPost<{
        run_id: string;
        signals: number;
        model: string;
        llm_cost_usd: number;
      }>("/api/agents/runs/sync", {
        account_id: accountId || null,
        extra_symbols: extras,
        force_rule: forceRule,
      });
      setMsg(
        `完成 run=${result.run_id.slice(0, 8)}… 信号 ${result.signals} · ${result.model} · $${result.llm_cost_usd}`,
      );
      await refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function openSignal(id: string) {
    const d = await apiGet<SignalDetail>(`/api/agents/signals/${id}`);
    setActive(d);
  }

  async function adopt() {
    if (!active || !accountId) return;
    try {
      const o = await apiPost<{ id: string; status: string }>(
        `/api/agents/signals/${active.id}/adopt`,
        { account_id: accountId },
      );
      setMsg(`已下模拟单 ${o.id.slice(0, 8)}… status=${o.status}`);
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function proposeLive() {
    if (!active) return;
    try {
      const o = await apiPost<{ id: string; status: string }>(
        `/api/agents/signals/${active.id}/propose-live`,
        {},
      );
      setMsg(`已推入实盘确认队列 ${o.id.slice(0, 8)}… status=${o.status}`);
    } catch (e) {
      setMsg(String(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Agent 决策"
        desc="技术/机构/多空辩论/交易员/风控 → buy/hold/sell。无 LLM key 时用规则引擎。"
      />
      {msg && <p className="alert alert-info">{msg}</p>}

      <div className="card card-padded" style={{ marginBottom: 20 }}>
        <div className="toolbar" style={{ margin: 0 }}>
          <label className="form-field">
            <span className="form-label">关联模拟账户</span>
            <select
              className="select"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">无</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-label">额外标的</span>
            <input className="input" value={extra} onChange={(e) => setExtra(e.target.value)} />
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={forceRule}
              onChange={(e) => setForceRule(e.target.checked)}
            />
            强制规则模式
          </label>
          <button type="button" className="btn btn-primary" onClick={runAgents} disabled={busy}>
            {busy ? "运行中…" : "运行决策"}
          </button>
        </div>
      </div>

      <div className="grid-2">
        <section className="card list-panel">
          <h3 className="list-section-title">最近信号</h3>
          {signals.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => openSignal(s.id)}
              className={`list-item${active?.id === s.id ? " list-item-active" : ""}`}
            >
              <div className="list-item-title">
                <span className="mono">{s.symbol}</span>
                <span className={actionBadgeClass(s.action)}>{s.action}</span>
              </div>
              <div className="list-item-meta">
                conf {s.confidence} · qty {s.suggested_qty} · {s.mode}
              </div>
              <div style={{ fontSize: 13, marginTop: 4, color: "var(--text)" }}>{s.summary}</div>
            </button>
          ))}
          {signals.length === 0 && <p className="empty-state">暂无信号</p>}

          <h3 className="list-section-title" style={{ borderTop: "1px solid var(--border-soft)" }}>
            运行记录
          </h3>
          <div style={{ padding: "0 18px 12px" }}>
            {runs.map((r) => (
              <div key={r.id} className="order-row">
                <div className="actions-row" style={{ justifyContent: "space-between" }}>
                  <span className="mono">{r.model}</span>
                  <span className={`badge ${r.status === "ok" ? "badge-success" : "badge-neutral"}`}>
                    {r.status}
                  </span>
                </div>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                  ${r.llm_cost_usd} · 候选 {r.candidate_count}
                  {r.error && <span className="text-danger"> · {r.error}</span>}
                </div>
              </div>
            ))}
            {runs.length === 0 && <p className="empty-state" style={{ padding: "16px 0" }}>暂无运行记录</p>}
          </div>
        </section>

        <section className="card card-padded">
          {!active && <p className="empty-state">选择信号查看角色对话。</p>}
          {active && (
            <>
              <div className="actions-row" style={{ justifyContent: "space-between" }}>
                <h2 className="detail-title" style={{ margin: 0 }}>
                  <span className="mono">{active.symbol}</span>
                  <span style={{ color: "var(--muted)", fontWeight: 400, margin: "0 8px" }}>→</span>
                  <span className={actionBadgeClass(active.action)}>{active.action}</span>
                </h2>
                {active.action !== "hold" && (
                  <div className="actions-row">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={adopt}
                      disabled={!accountId}
                    >
                      采纳 → 下模拟单
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={proposeLive}>
                      推入实盘确认
                    </button>
                  </div>
                )}
              </div>
              <p className="detail-sub">
                置信度 <b style={{ color: "var(--text)" }}>{active.confidence}</b> · 建议数量{" "}
                <b style={{ color: "var(--text)" }}>{active.suggested_qty}</b>
              </p>
              <div className="form-stack" style={{ maxWidth: "none", marginTop: 12 }}>
                {ROLES.map(([key, label]) => {
                  const val = active.reason?.[key];
                  const text =
                    typeof val === "string" ? val : val ? JSON.stringify(val, null, 2) : "—";
                  return (
                    <div key={key} className="role-card">
                      <div className="role-label">{label}</div>
                      <pre className="role-body">{text}</pre>
                    </div>
                  );
                })}
                {active.reason?.summary != null && (
                  <p>
                    <b>摘要:</b> {String(active.reason.summary)}
                  </p>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
