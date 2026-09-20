"use client";

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiGet, apiPost } from "@/lib/api";

type Job = {
  id: string;
  status: string;
  producer: string;
  last_loop: number;
  best_ic: number | null;
  llm_cost_usd: number;
  error: string;
  strategy_id: string | null;
  created_at: string;
  finished_at: string | null;
  runner_target?: { type?: string; host?: string };
};

type Event = {
  type: string;
  seq: number;
  payload: Record<string, unknown>;
  created_at: string;
};

type Strategy = {
  id: string;
  name: string;
  producer: string;
  metrics: Record<string, number>;
  verified_metrics: Record<string, unknown>;
  status: string;
};

export default function ResearchPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [sshHost, setSshHost] = useState("");
  const [sshUser, setSshUser] = useState("ubuntu");

  const refresh = useCallback(async () => {
    const [j, s] = await Promise.all([
      apiGet<Job[]>("/api/research/jobs"),
      apiGet<Strategy[]>("/api/research/strategies"),
    ]);
    setJobs(j);
    setStrategies(s);
  }, []);

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
    const t = setInterval(() => {
      refresh().catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    apiGet<Job & { events: Event[] }>(`/api/research/jobs/${selected}`)
      .then((d) => setEvents(d.events || []))
      .catch((e) => setMsg(String(e)));
  }, [selected, jobs]);

  async function createAndStartAlphaLocal() {
    setBusy(true);
    setMsg("");
    try {
      const job = await apiPost<Job>("/api/research/jobs", {
        producer: "alphaagent",
        max_loops: 3,
        runner_type: "local_docker",
      });
      await apiPost(`/api/research/jobs/${job.id}/start`, { use_docker: false });
      setSelected(job.id);
      await refresh();
      setMsg(`AlphaAgent 本地任务已启动 ${job.id.slice(0, 8)}…`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createAndStartRdRemote() {
    if (!sshHost.trim() || !sshUser.trim()) {
      setMsg("RD-Agent 远程任务需要填写 SSH 主机与用户");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const job = await apiPost<Job>("/api/research/jobs", {
        producer: "rdagent",
        scenario: "fin_factor",
        max_loops: 3,
        runner_type: "remote_ssh",
        ssh_host: sshHost.trim(),
        ssh_user: sshUser.trim(),
        ssh_key_ref: "env:RUNNER_SSH_KEY",
      });
      await apiPost(`/api/research/jobs/${job.id}/start`, { use_remote: true });
      setSelected(job.id);
      await refresh();
      setMsg(`RD-Agent 远程任务已启动 ${job.id.slice(0, 8)}…`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createAndStartAlphaRemote() {
    if (!sshHost.trim() || !sshUser.trim()) {
      setMsg("远程任务需要填写 SSH 主机与用户");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const job = await apiPost<Job>("/api/research/jobs", {
        producer: "alphaagent",
        max_loops: 3,
        runner_type: "remote_ssh",
        ssh_host: sshHost.trim(),
        ssh_user: sshUser.trim(),
        ssh_key_ref: "env:RUNNER_SSH_KEY",
      });
      await apiPost(`/api/research/jobs/${job.id}/start`, { use_remote: true });
      setSelected(job.id);
      await refresh();
      setMsg(`AlphaAgent 远程任务已启动 ${job.id.slice(0, 8)}…`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function retry(id: string) {
    setBusy(true);
    try {
      await apiPost(`/api/research/jobs/${id}/retry`, {});
      await refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function genSignals(id: string) {
    setBusy(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const r = await apiPost<{ count: number }>(`/api/research/strategies/${id}/signals`, {
        trade_date: today,
      });
      setMsg(`已生成 ${r.count} 条信号`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  function statusBadge(s: string) {
    if (s === "ok" || s === "done" || s === "completed") return "badge badge-success";
    if (s === "lost" || s === "failed" || s === "error") return "badge badge-danger";
    if (s === "running" || s === "pending") return "badge badge-pending";
    return "badge badge-neutral";
  }

  return (
    <div>
      <div className="page-header-row">
        <PageHeader
          title="研究任务"
          desc="双框架：AlphaAgent（本地/远程）+ RD-Agent（建议 Linux x86 远程）→ 策略包入库 → 信号"
        />
        <div className="page-header-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={createAndStartAlphaLocal}
          >
            AlphaAgent 本地
          </button>
        </div>
      </div>

      <div className="card card-padded" style={{ marginBottom: 20 }}>
        <div className="toolbar" style={{ margin: 0 }}>
          <label className="form-field">
            <span className="form-label">SSH 主机</span>
            <input
              className="input"
              value={sshHost}
              onChange={(e) => setSshHost(e.target.value)}
              placeholder="远端 runner 主机 IP"
            />
          </label>
          <label className="form-field">
            <span className="form-label">用户</span>
            <input className="input" value={sshUser} onChange={(e) => setSshUser(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={createAndStartRdRemote}
          >
            RD-Agent 远程
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={createAndStartAlphaRemote}
          >
            AlphaAgent 远程
          </button>
        </div>
      </div>

      {msg && (
        <p className={`alert ${/Error:|failed|失败/i.test(msg) ? "alert-error" : "alert-info"}`}>
          {msg}
        </p>
      )}

      <section className="section-block">
        <h2 className="section-title">任务</h2>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>框架</th>
                <th>目标</th>
                <th>状态</th>
                <th className="num">轮次</th>
                <th className="num">IC</th>
                <th className="num">费用</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr
                  key={j.id}
                  className="clickable"
                  onClick={() => setSelected(j.id)}
                >
                  <td className="mono">{j.id.slice(0, 8)}</td>
                  <td>{j.producer}</td>
                  <td style={{ fontSize: 13, color: "var(--muted)" }}>
                    {j.runner_target?.type === "remote_ssh"
                      ? `ssh:${j.runner_target.host || "?"}`
                      : "local"}
                  </td>
                  <td><span className={statusBadge(j.status)}>{j.status}</span></td>
                  <td className="num">{j.last_loop}</td>
                  <td className="num">{j.best_ic ?? "—"}</td>
                  <td className="num">${j.llm_cost_usd.toFixed(2)}</td>
                  <td>
                    {j.status === "lost" && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          retry(j.id);
                        }}
                      >
                        重试
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={8} className="empty-state">
                    暂无任务
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="section-block card card-padded">
          <h2 className="section-title">事件流 · {selected.slice(0, 8)}</h2>
          <ol style={{ fontSize: 13, color: "var(--muted)", paddingLeft: 18, margin: 0 }}>
            {events.map((e) => (
              <li key={`${e.seq}-${e.type}`} style={{ marginBottom: 6 }}>
                <code>#{e.seq}</code> {e.type}
                {e.payload?.loop != null && ` loop=${e.payload.loop}`}
                {e.payload?.best_ic != null && ` ic=${e.payload.best_ic}`}
                {e.payload?.message != null && ` — ${String(e.payload.message)}`}
              </li>
            ))}
            {!events.length && <li>暂无事件</li>}
          </ol>
        </section>
      )}

      <section className="section-block">
        <h2 className="section-title">已入库策略</h2>
        <div className="card list-panel">
          {strategies.map((s) => (
            <div
              key={s.id}
              className="list-item"
              style={{ cursor: "default" }}
            >
              <div className="actions-row" style={{ justifyContent: "space-between", width: "100%" }}>
                <div>
                  <strong>{s.name}</strong>
                  <div className="list-item-meta">
                    {s.producer} · claimed IC {s.metrics?.ic ?? "—"} · verified{" "}
                    {String(s.verified_metrics?.sample_ic ?? s.verified_metrics?.verify_skipped ?? "—")}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => genSignals(s.id)}
                >
                  生成今日信号
                </button>
              </div>
            </div>
          ))}
          {!strategies.length && (
            <p className="empty-state">尚无策略，先跑一轮任务</p>
          )}
        </div>
      </section>
    </div>
  );
}
