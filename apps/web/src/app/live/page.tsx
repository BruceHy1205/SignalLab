"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiGet, apiPost } from "@/lib/api";

type Intent = {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
  source: string;
  note: string;
  broker: string;
  broker_order_id: string | null;
  error: string;
  created_at: string;
};

function statusBadge(s: string) {
  if (s === "submitted" || s === "filled") return "badge badge-success";
  if (s === "rejected" || s === "failed") return "badge badge-danger";
  if (s === "pending_confirm") return "badge badge-pending";
  return "badge badge-neutral";
}

export default function LivePage() {
  const [intents, setIntents] = useState<Intent[]>([]);
  const [filter, setFilter] = useState("pending_confirm");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [symbol, setSymbol] = useState("600519.SH");
  const [side, setSide] = useState("buy");
  const [qty, setQty] = useState(100);

  const refresh = useCallback(async () => {
    const q = filter ? `?status=${encodeURIComponent(filter)}` : "";
    const rows = await apiGet<Intent[]>(`/api/live/intents${q}`);
    setIntents(rows);
  }, [filter]);

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
  }, [refresh]);

  async function create() {
    setBusy(true);
    setMsg("");
    try {
      await apiPost("/api/live/intents", {
        symbol,
        side,
        quantity: qty,
        note: "manual",
      });
      await refresh();
      setMsg("已创建待确认意图");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(id: string) {
    setBusy(true);
    try {
      await apiPost(`/api/live/intents/${id}/confirm`, {});
      await refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reject(id: string) {
    setBusy(true);
    try {
      await apiPost(`/api/live/intents/${id}/reject`, {});
      await refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="实盘确认队列"
        desc="所有实盘意图默认待确认；确认后才提交 broker（默认 stub，可配 miniqmt）"
      />

      <div className="card card-padded" style={{ marginBottom: 20 }}>
        <div className="toolbar" style={{ margin: 0 }}>
          <label className="form-field">
            <span className="form-label">代码</span>
            <input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          </label>
          <label className="form-field">
            <span className="form-label">方向</span>
            <select className="select" value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="buy">买入</option>
              <option value="sell">卖出</option>
            </select>
          </label>
          <label className="form-field">
            <span className="form-label">数量</span>
            <input
              className="input"
              type="number"
              value={qty}
              onChange={(e) => setQty(Number(e.target.value))}
              style={{ width: 120 }}
            />
          </label>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={create}>
            新建意图
          </button>
          <label className="form-field" style={{ marginLeft: "auto" }}>
            <span className="form-label">筛选</span>
            <select className="select" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="pending_confirm">待确认</option>
              <option value="submitted">已提交</option>
              <option value="rejected">已拒绝</option>
              <option value="failed">失败</option>
              <option value="">全部</option>
            </select>
          </label>
        </div>
      </div>

      {msg && <p className="alert alert-info">{msg}</p>}

      <div className="table-wrap section-block">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>标的</th>
              <th>方向</th>
              <th className="num">数量</th>
              <th>状态</th>
              <th>来源</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {intents.map((i) => (
              <tr key={i.id}>
                <td className="mono">{i.id.slice(0, 8)}</td>
                <td className="mono">{i.symbol}</td>
                <td>
                  <span className={`badge ${i.side === "buy" ? "badge-buy" : "badge-sell"}`}>
                    {i.side}
                  </span>
                </td>
                <td className="num">{i.quantity}</td>
                <td><span className={statusBadge(i.status)}>{i.status}</span></td>
                <td className="text-muted">{i.source}</td>
                <td>
                  <div className="actions-row">
                    {i.status === "pending_confirm" && (
                      <>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={busy}
                          onClick={() => confirm(i.id)}
                        >
                          确认下单
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={busy}
                          onClick={() => reject(i.id)}
                        >
                          拒绝
                        </button>
                      </>
                    )}
                    {i.broker_order_id && (
                      <span className="text-muted mono" style={{ fontSize: 12 }}>{i.broker_order_id}</span>
                    )}
                    {i.error && <span className="text-danger" style={{ fontSize: 12 }}>{i.error}</span>}
                  </div>
                </td>
              </tr>
            ))}
            {!intents.length && (
              <tr>
                <td colSpan={7} className="empty-state">
                  暂无意图
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
