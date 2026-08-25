"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch } from "@/lib/api";
import { SettingsPageHeader } from "@/components/settings/shared";

export default function TokenSaverSettingsPage() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(true);
  const [ratio, setRatio] = useState(0.7);
  const [bounds, setBounds] = useState<[number, number]>([0.1, 0.95]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    void (async () => {
      const res = await apiFetch("/api/v1/settings/token-budget");
      if (res.ok) {
        const data = await res.json();
        setEnabled(Boolean(data.settings?.enabled ?? true));
        setRatio(Number(data.settings?.context_ratio ?? 0.7));
        if (Array.isArray(data.bounds?.context_ratio)) {
          setBounds(data.bounds.context_ratio);
        }
      }
    })();
  }, []);

  async function save() {
    setSaving(true);
    try {
      const res = await apiFetch("/api/v1/settings/token-budget", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, context_ratio: ratio }),
      });
      setMsg(res.ok ? "已保存" : await res.text());
    } finally {
      setSaving(false);
    }
  }

  const [min, max] = bounds;

  return (
    <div>
      <SettingsPageHeader
        title={t("节省 Token", "节省 Token")}
        description={t(
          "tokenSaver.description",
          "上下文压缩策略：开启时使用三级注入 + 有界历史（早期对话自动摘要）；关闭时把完整历史、注入块与用户画像全部发送给模型，直到达到上下文窗口的设定比例才自动压缩。",
        )}
      />
      <div className="mt-6 max-w-2xl space-y-6 rounded-xl border p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">{t("启用上下文压缩", "启用上下文压缩")}</div>
            <div className="mt-1 text-sm opacity-60">
              {enabled
                ? "开启：三级注入块 + 历史有界（约 4000 tokens 后自动摘要早期对话）。"
                : "关闭：完整上下文直达模型（含全部历史、注入块与用户画像）。"}
            </div>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            className={
              enabled
                ? "rounded-full bg-emerald-500 px-4 py-1.5 text-sm text-white"
                : "rounded-full bg-gray-500 px-4 py-1.5 text-sm text-white"
            }
          >
            {enabled ? "开" : "关"}
          </button>
        </div>

        {!enabled && (
          <div className="space-y-3 rounded-lg bg-black/5 p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("上下文触发比例", "上下文触发比例")}</div>
                <div className="mt-1 text-sm opacity-60">
                  达到模型上下文窗口的该比例时开始自动压缩（如 DeepSeek V4 的 1M 窗口 × 70% ≈ 70 万 tokens）。
                </div>
              </div>
              <span className="font-mono text-lg">{Math.round(ratio * 100)}%</span>
            </div>
            <input
              type="range"
              min={min}
              max={max}
              step={0.05}
              value={ratio}
              onChange={(e) => setRatio(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex items-center gap-2">
              <span className="text-xs opacity-50">或手动输入：</span>
              <input
                type="number"
                min={Math.round(min * 100)}
                max={Math.round(max * 100)}
                value={Math.round(ratio * 100)}
                onChange={(e) => {
                  const v = Number(e.target.value) / 100;
                  if (!Number.isNaN(v)) setRatio(Math.max(min, Math.min(max, v)));
                }}
                className="w-24 rounded-md border bg-transparent px-2 py-1 text-sm"
              />
              <span className="text-xs opacity-50">%</span>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="rounded-md bg-blue-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
          {msg && <span className="text-sm text-amber-600">{msg}</span>}
        </div>
      </div>
    </div>
  );
}
