"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiGet, pct, type LeaderRow } from "@/lib/api";

export default function LeaderboardPage() {
  const [windowDays, setWindowDays] = useState(5);
  const [rows, setRows] = useState<LeaderRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setErr(null);
    apiGet<LeaderRow[]>(`/api/tracker/leaderboard?window_days=${windowDays}`)
      .then(setRows)
      .catch((e) => setErr(String(e)));
  }, [windowDays]);

  return (
    <div>
      <PageHeader title="机构排行" desc="仅统计 confidence=explicit 且已锚定的推荐。" />

      <div className="chip-group">
        {[1, 3, 5, 10, 20, 60].map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => setWindowDays(w)}
            className={`chip${windowDays === w ? " chip-active" : ""}`}
          >
            T+{w}
          </button>
        ))}
      </div>

      {err && <p className="alert alert-error">{err}</p>}

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>机构</th>
              <th className="num">样本</th>
              <th className="num">胜率</th>
              <th className="num">平均收益</th>
              <th className="num">平均超额</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.source_id}>
                <td style={{ fontWeight: 500 }}>{r.name}</td>
                <td className="num">{r.n}</td>
                <td className="num">{pct(r.win_rate)}</td>
                <td className="num">{pct(r.avg_abs)}</td>
                <td className="num">{pct(r.avg_excess)}</td>
              </tr>
            ))}
            {rows.length === 0 && !err && (
              <tr>
                <td colSpan={5} className="empty-state">
                  暂无数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
