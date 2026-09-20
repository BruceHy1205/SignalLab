"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { RecChart } from "@/components/RecChart";
import { apiGet, pct, type RecDetail, type Recommendation } from "@/lib/api";

function actionBadgeClass(action: string) {
  const a = action?.toLowerCase();
  if (a === "buy") return "badge badge-buy";
  if (a === "sell") return "badge badge-sell";
  if (a === "hold") return "badge badge-hold";
  return "badge badge-neutral";
}

export default function HomePage() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [active, setActive] = useState<RecDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Recommendation[]>("/api/tracker/recommendations?limit=50")
      .then(setRecs)
      .catch((e) => setErr(String(e)));
  }, []);

  async function openRec(id: string) {
    const d = await apiGet<RecDetail>(`/api/tracker/recommendations/${id}`);
    setActive(d);
  }

  return (
    <div>
      <PageHeader
        title="推荐追踪"
        desc="根据机构聊天推荐锚定基准价,追踪 T+N 收益与相对沪深300超额。"
      />
      {err && <p className="alert alert-error">{err}</p>}

      <div className="grid-2">
        <div className="card list-panel">
          {recs.length === 0 && !err && (
            <p className="empty-state">
              暂无推荐,先去<a href="/import">「导入」</a>。
            </p>
          )}
          {recs.length === 0 && err && (
            <p className="empty-state">暂时无法加载推荐列表</p>
          )}
          {recs.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => openRec(r.id)}
              className={`list-item${active?.id === r.id ? " list-item-active" : ""}`}
            >
              <div className="list-item-title">
                <span>
                  {r.symbol_name}
                  {r.symbol ? <span className="text-muted" style={{ fontWeight: 400, marginLeft: 6 }}>{r.symbol}</span> : null}
                </span>
                <span className={actionBadgeClass(r.action)}>{r.action}</span>
              </div>
              <div className="list-item-meta">
                {r.message_time?.slice(0, 16)} · {r.confidence} · {r.status}
              </div>
            </button>
          ))}
        </div>

        <div className="card card-padded" style={{ minHeight: 380 }}>
          {!active && <p className="empty-state">选择左侧一条推荐查看走势。</p>}
          {active && (
            <>
              <div className="actions-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                <h2 className="detail-title" style={{ margin: 0 }}>
                  {active.symbol_name}
                  {active.symbol ? <span className="text-muted mono" style={{ marginLeft: 8, fontWeight: 400 }}>{active.symbol}</span> : null}
                </h2>
                <span className={actionBadgeClass(active.action)}>{active.action}</span>
              </div>
              {active.baseline_price != null && (
                <p className="detail-sub">
                  基准 <b style={{ color: "var(--text)" }}>{active.baseline_price.toFixed(2)}</b> · {active.baseline_rule}
                </p>
              )}
              <p className="detail-sub" style={{ whiteSpace: "pre-wrap" }}>
                {active.raw_text}
              </p>
              <RecChart rec={active} />
              {active.performances[0] && (
                <p className="metric-row">
                  例:T+5 绝对{" "}
                  <b>{pct(active.performances.find((p) => p.window_days === 5)?.abs_return)}</b>
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
