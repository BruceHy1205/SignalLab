"use client";

import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";

import { apiGet, pct, type RecDetail } from "@/lib/api";

type BarPoint = {
  trade_date: string;
  close: number;
};

function hexToRgb(hex: string): string | null {
  const m = hex.trim().replace("#", "");
  if (m.length !== 6) return null;
  const r = parseInt(m.slice(0, 2), 16);
  const g = parseInt(m.slice(2, 4), 16);
  const b = parseInt(m.slice(4, 6), 16);
  if ([r, g, b].some((n) => Number.isNaN(n))) return null;
  return `${r},${g},${b}`;
}

export function RecChart({ rec }: { rec: RecDetail }) {
  const [bars, setBars] = useState<BarPoint[]>([]);
  const [bench, setBench] = useState<BarPoint[]>([]);

  useEffect(() => {
    if (!rec.symbol || !rec.baseline_date) return;
    const start = rec.baseline_date;
    const end = new Date().toISOString().slice(0, 10);
    Promise.all([
      apiGet<BarPoint[]>(
        `/api/datahub/bars?symbol=${encodeURIComponent(rec.symbol)}&start=${start}&end=${end}`,
      ),
      apiGet<BarPoint[]>(
        `/api/datahub/bars?symbol=000300.SH&start=${start}&end=${end}`,
      ).catch(() => [] as BarPoint[]),
    ]).then(([s, b]) => {
      setBars(s);
      setBench(b);
    });
  }, [rec.symbol, rec.baseline_date]);

  if (!rec.baseline_price || bars.length === 0) {
    return (
      <p className="detail-sub">
        暂无行情(请先同步日线)。窗口指标仍可查看。
      </p>
    );
  }

  const base = rec.baseline_price;
  const dates = bars.map((b) => b.trade_date);
  const stockNorm = bars.map((b) => +((b.close / base) * 100).toFixed(2));
  const bench0 = bench[0]?.close;
  const benchNorm =
    bench0 && bench.length
      ? dates.map((d) => {
          const p = bench.find((x) => x.trade_date === d);
          return p ? +((p.close / bench0) * 100).toFixed(2) : null;
        })
      : [];

  const css = getComputedStyle(document.documentElement);
  const cText = css.getPropertyValue("--text").trim() || "#0f172a";
  const cMuted = css.getPropertyValue("--muted").trim() || "#64748b";
  const cMuted2 = css.getPropertyValue("--muted-2").trim() || "#94a3b8";
  const cAccent = css.getPropertyValue("--accent").trim() || "#2563eb";
  const cBorder = css.getPropertyValue("--border").trim() || "#e2e8f0";
  const cSurface = css.getPropertyValue("--surface").trim() || "#ffffff";
  const cSurface2 = css.getPropertyValue("--surface-2").trim() || "#f1f5f9";
  const accentRgb = hexToRgb(cAccent) || "37,99,235";

  const option = {
    grid: { left: 48, right: 24, top: 36, bottom: 40 },
    tooltip: {
      trigger: "axis",
      backgroundColor: cSurface,
      borderColor: cBorder,
      borderWidth: 1,
      textStyle: { color: cText, fontSize: 13 },
      extraCssText: "box-shadow: 0 4px 12px rgba(0,0,0,0.18); border-radius: 8px;",
    },
    legend: { data: [rec.symbol_name, "沪深300"], top: 0, textStyle: { color: cMuted } },
    xAxis: {
      type: "category",
      data: dates,
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
        name: rec.symbol_name,
        type: "line",
        data: stockNorm,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: cAccent },
        areaStyle: { color: `rgba(${accentRgb},0.12)` },
        markLine: {
          symbol: "none",
          data: [{ xAxis: rec.baseline_date }],
          lineStyle: { color: cMuted, type: "dashed" },
          label: { formatter: "推荐日", color: cMuted },
        },
      },
      benchNorm.length
        ? {
            name: "沪深300",
            type: "line",
            data: benchNorm,
            showSymbol: false,
            lineStyle: { width: 1.5, color: cMuted2, type: "dashed" },
          }
        : null,
    ].filter(Boolean),
  };

  return (
    <div>
      <ReactECharts option={option} style={{ height: 320 }} />
      <div className="metric-row">
        {rec.performances.map((p) => (
          <span key={p.window_days}>
            T+{p.window_days}: <b>{pct(p.abs_return)}</b>
            {p.excess_return != null && <> / 超额 {pct(p.excess_return)}</>}
          </span>
        ))}
      </div>
    </div>
  );
}
