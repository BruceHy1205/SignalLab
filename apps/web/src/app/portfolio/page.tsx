"use client";

import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiGet, apiPost, pct } from "@/lib/api";

type Account = {
  id: string;
  name: string;
  cash: number;
  initial_cash: number;
  performance?: {
    total_return: number | null;
    annualized: number | null;
    max_drawdown: number | null;
    excess_return: number | null;
  };
};

type Position = { symbol: string; quantity: number; avg_cost: number };
type NavPoint = {
  trade_date: string;
  cash: number;
  market_value: number;
  nav: number;
  bench_nav: number | null;
};
type Order = {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
  fill_price: number | null;
  reject_reason: string | null;
  submitted_at: string;
};

function Stat({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  return (
    <div className="card stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={tone === "pos" ? { color: "var(--success)" } : tone === "neg" ? { color: "var(--danger)" } : undefined}>
        {value}
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<string>("");
  const [detail, setDetail] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [nav, setNav] = useState<NavPoint[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [symbol, setSymbol] = useState("600519");
  const [qty, setQty] = useState(100);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [newName, setNewName] = useState("默认组合");
  const [runDate, setRunDate] = useState(new Date().toISOString().slice(0, 10));
  const [msg, setMsg] = useState<string | null>(null);

  async function refreshList() {
    const list = await apiGet<Account[]>("/api/papertrade/accounts");
    setAccounts(list);
    if (!accountId && list[0]) setAccountId(list[0].id);
  }

  async function refreshDetail(id: string) {
    const [d, p, n, o] = await Promise.all([
      apiGet<Account>(`/api/papertrade/accounts/${id}`),
      apiGet<Position[]>(`/api/papertrade/accounts/${id}/positions`),
      apiGet<NavPoint[]>(`/api/papertrade/accounts/${id}/nav`),
      apiGet<Order[]>(`/api/papertrade/accounts/${id}/orders`),
    ]);
    setDetail(d);
    setPositions(p);
    setNav(n);
    setOrders(o);
  }

  useEffect(() => {
    refreshList().catch((e) => setMsg(String(e)));
  }, []);

  useEffect(() => {
    if (accountId) refreshDetail(accountId).catch((e) => setMsg(String(e)));
  }, [accountId]);

  async function createAccount() {
    const a = await apiPost<Account>("/api/papertrade/accounts", {
      name: newName,
      initial_cash: 1_000_000,
    });
    await refreshList();
    setAccountId(a.id);
    setMsg(`已创建账户 ${a.name}`);
  }

  async function placeOrder() {
    if (!accountId) return;
    await apiPost(`/api/papertrade/accounts/${accountId}/orders`, {
      symbol,
      side,
      quantity: qty,
    });
    await refreshDetail(accountId);
    setMsg("订单已提交(pending),需 run-day 后按次日开盘成交");
  }

  async function runDay() {
    const r = await apiPost<Record<string, number>>("/api/papertrade/run-day", {
      trade_date: runDate,
      account_id: accountId || null,
    });
    if (accountId) await refreshDetail(accountId);
    setMsg(`日终完成: ${JSON.stringify(r)}`);
  }

  const nav0 = nav[0]?.nav;
  const bench0 = nav.find((x) => x.bench_nav)?.bench_nav;
  const css = typeof document !== "undefined" ? getComputedStyle(document.documentElement) : null;
  const cText = css?.getPropertyValue("--text").trim() || "#0f172a";
  const cMuted = css?.getPropertyValue("--muted").trim() || "#64748b";
  const cMuted2 = css?.getPropertyValue("--muted-2").trim() || "#94a3b8";
  const cAccent = css?.getPropertyValue("--accent").trim() || "#2563eb";
  const cBorder = css?.getPropertyValue("--border").trim() || "#e2e8f0";
  const cSurface = css?.getPropertyValue("--surface").trim() || "#ffffff";
  const cSurface2 = css?.getPropertyValue("--surface-2").trim() || "#f1f5f9";
  const accentRgb = (cAccent.replace("#", "").match(/.{2}/g) || []).map((h) => parseInt(h, 16)).join(",");
  const chartOption = {
    grid: { left: 48, right: 24, top: 36, bottom: 36 },
    tooltip: {
      trigger: "axis",
      backgroundColor: cSurface,
      borderColor: cBorder,
      borderWidth: 1,
      textStyle: { color: cText, fontSize: 13 },
      extraCssText: "box-shadow: 0 4px 12px rgba(0,0,0,0.18); border-radius: 8px;",
    },
    legend: { data: ["组合净值", "沪深300"], textStyle: { color: cMuted }, top: 0 },
    xAxis: {
      type: "category",
      data: nav.map((p) => p.trade_date),
      axisLine: { lineStyle: { color: cBorder } },
      axisLabel: { color: cMuted2 },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: cSurface2 } },
      axisLabel: { color: cMuted2 },
    },
    series: [
      {
        name: "组合净值",
        type: "line",
        showSymbol: false,
        smooth: true,
        data: nav.map((p) => (nav0 ? +((p.nav / nav0) * 100).toFixed(2) : p.nav)),
        lineStyle: { color: cAccent, width: 2 },
        areaStyle: { color: `rgba(${accentRgb},0.12)` },
      },
      {
        name: "沪深300",
        type: "line",
        showSymbol: false,
        data: nav.map((p) =>
          bench0 && p.bench_nav ? +((p.bench_nav / bench0) * 100).toFixed(2) : null,
        ),
        lineStyle: { color: cMuted2, width: 1.5, type: "dashed" },
      },
    ],
  };

  const perf = detail?.performance;

  return (
    <div>
      <PageHeader
        title="模拟盘"
        desc="次日开盘撮合 · A股整手 · 佣金/印花税/滑点 · 收盘盯市净值"
      />
      {msg && <p className="alert alert-info">{msg}</p>}

      <div className="toolbar">
        <label className="form-field">
          <span className="form-label">账户</span>
          <select
            className="select"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span className="form-label">新账户名</span>
          <input
            className="input"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
        </label>
        <button type="button" className="btn btn-secondary" onClick={createAccount}>
          创建账户
        </button>
      </div>

      {detail && (
        <div className="grid-stats">
          <Stat label="现金" value={detail.cash.toFixed(2)} />
          <Stat
            label="累计收益"
            value={pct(perf?.total_return ?? null)}
            tone={perf?.total_return != null ? (perf.total_return >= 0 ? "pos" : "neg") : undefined}
          />
          <Stat
            label="最大回撤"
            value={pct(perf?.max_drawdown ?? null)}
            tone={perf?.max_drawdown != null ? "neg" : undefined}
          />
          <Stat
            label="超额(沪深300)"
            value={pct(perf?.excess_return ?? null)}
            tone={perf?.excess_return != null ? (perf.excess_return >= 0 ? "pos" : "neg") : undefined}
          />
        </div>
      )}

      <div className="card chart-wrap" style={{ marginBottom: 20 }}>
        {nav.length > 0 ? (
          <ReactECharts option={chartOption} style={{ height: 300 }} />
        ) : (
          <p className="empty-state">暂无净值,下单并 run-day 后生成。</p>
        )}
      </div>

      <div className="grid-split">
        <section className="card card-padded">
          <h3 className="section-title">下单</h3>
          <div className="form-stack" style={{ maxWidth: "none" }}>
            <div className="grid-split" style={{ gap: 12 }}>
              <input
                className="input"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="代码"
              />
              <select
                className="select"
                value={side}
                onChange={(e) => setSide(e.target.value as "buy" | "sell")}
              >
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
              </select>
            </div>
            <input
              className="input"
              type="number"
              value={qty}
              onChange={(e) => setQty(Number(e.target.value))}
              placeholder="数量"
            />
            <button type="button" className="btn btn-primary" onClick={placeOrder}>
              提交订单
            </button>
            <div className="actions-row" style={{ marginTop: 4 }}>
              <label className="form-field" style={{ flex: 1 }}>
                <span className="form-label">交易日</span>
                <input
                  className="input"
                  type="date"
                  value={runDate}
                  onChange={(e) => setRunDate(e.target.value)}
                />
              </label>
              <button type="button" className="btn btn-secondary" onClick={runDay}>
                执行日终
              </button>
            </div>
          </div>

          <h4 className="section-title" style={{ marginTop: 24 }}>
            持仓
          </h4>
          <div className="table-wrap card-flat" style={{ boxShadow: "none" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th className="num">数量</th>
                  <th className="num">成本</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol}>
                    <td className="mono">{p.symbol}</td>
                    <td className="num">{p.quantity}</td>
                    <td className="num">{p.avg_cost.toFixed(2)}</td>
                  </tr>
                ))}
                {positions.length === 0 && (
                  <tr>
                    <td colSpan={3} className="empty-state">
                      空仓
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card card-padded">
          <h3 className="section-title">订单</h3>
          <div className="scroll-panel">
            {orders.map((o) => (
              <div key={o.id} className="order-row">
                <div className="actions-row" style={{ justifyContent: "space-between" }}>
                  <b>
                    {o.side === "buy" ? "买入" : "卖出"} {o.symbol} × {o.quantity}
                  </b>
                  <span className={`badge ${o.status === "filled" ? "badge-success" : "badge-pending"}`}>
                    {o.status}
                  </span>
                </div>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                  {o.fill_price != null && `成交价 ${o.fill_price.toFixed(2)} · `}
                  {o.submitted_at?.slice(0, 16)}
                  {o.reject_reason && <span className="text-danger"> · {o.reject_reason}</span>}
                </div>
              </div>
            ))}
            {orders.length === 0 && <p className="empty-state">暂无订单</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
