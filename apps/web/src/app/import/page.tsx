"use client";

import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { apiPost } from "@/lib/api";

export default function ImportPage() {
  const [sourceName, setSourceName] = useState("XX投顾");
  const [format, setFormat] = useState<"paste" | "wechat">("paste");
  const [content, setContent] = useState(
    "2026-07-01 10:00\n今天重点关注茅台,建议逢低吸纳,目标1900\n\n2026-07-02 15:30\n宁德时代可以减仓了",
  );
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setResult(null);
    try {
      const r = await apiPost<{ created: number; skipped: number; pending: number }>(
        "/api/tracker/import",
        { content, source_name: sourceName, format },
      );
      setResult(`创建 ${r.created}, 跳过 ${r.skipped}, 待消歧 ${r.pending}`);
    } catch (e) {
      setResult(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="导入聊天记录"
        desc="支持微信导出 txt 或手动粘贴。未配置 LLM 时使用规则粗抽(已知热门股)。"
      />

      <div className="card card-padded" style={{ maxWidth: 760 }}>
        <div className="form-stack" style={{ maxWidth: "none" }}>
          <div className="grid-split" style={{ gap: 16 }}>
            <label className="form-field">
              <span className="form-label">机构/来源名</span>
              <input
                className="input"
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
              />
            </label>
            <label className="form-field">
              <span className="form-label">格式</span>
              <select
                className="select"
                value={format}
                onChange={(e) => setFormat(e.target.value as "paste" | "wechat")}
              >
                <option value="paste">粘贴文本</option>
                <option value="wechat">微信导出</option>
              </select>
            </label>
          </div>
          <label className="form-field">
            <span className="form-label">内容</span>
            <textarea
              className="textarea textarea-mono"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={12}
            />
          </label>
          <div className="actions-row">
            <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "导入中…" : "导入"}
            </button>
            {result && <span className="alert alert-info" style={{ margin: 0 }}>{result}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
