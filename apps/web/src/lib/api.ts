export type Recommendation = {
  id: string;
  source_id: string;
  message_time: string;
  symbol: string | null;
  symbol_name: string;
  action: string;
  confidence: string;
  target_price: number | null;
  stop_loss: number | null;
  status: string;
  baseline_date: string | null;
  baseline_price: number | null;
  baseline_rule: string | null;
  reason: string;
};

export type Performance = {
  window_days: number;
  abs_return: number | null;
  excess_return: number | null;
  max_drawdown: number | null;
  max_runup: number | null;
  as_of_date: string | null;
};

export type RecDetail = Recommendation & {
  raw_text: string;
  performances: Performance[];
};

export type LeaderRow = {
  source_id: string;
  name: string;
  n: number;
  avg_abs: number | null;
  avg_excess: number | null;
  win_rate: number | null;
};

export function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

const API = "";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}
