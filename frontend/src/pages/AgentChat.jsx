/** AI Chat — Four-role Agent team */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";

const ROLES = [
  { key: "Planner", color: "#6366f1", labelKey: "agent.rolePlanner" },
  { key: "Executor", color: "#10b981", labelKey: "agent.roleExecutor" },
  { key: "Critic", color: "#f59e0b", labelKey: "agent.roleCritic" },
  { key: "Referee", color: "#ef4444", labelKey: "agent.roleReferee" },
];

/** 急救强提示样式：红色警示，必须醒目，不可被忽略 */
const EMERGENCY_STYLE = {
  background: "#fef2f2",
  border: "2px solid #dc2626",
  borderRadius: "10px",
  padding: "16px",
  marginBottom: "12px",
};

export default function AgentChat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // 急救拦截状态：null | { signal, guidance }
  const [emergency, setEmergency] = useState(null);

  async function send() {
    if (!input.trim() || loading) return;
    const text = input.trim();
    setEmergency(null);

    /* ---- 步骤 1：健康护栏预检 ----
     * 命中紧急信号 → 渲染强提示，终止后续请求（不消耗 Agent 算力，
     * 也不让 Agent 在紧急场景下给出 wellness 建议造成延误）。 */
    try {
      const res = await api.emergencyCheck(text);
      const data = await res.json();
      if (data && data.is_emergency) {
        setEmergency({ signal: data.signal, guidance: data.guidance });
        setInput("");
        return;
      }
    } catch {
      /* 预检失败不阻断主流程——中间件仍会兜底拦截 */
    }

    /* ---- 步骤 2：正常发起 Agent 请求 ---- */
    const userMsg = { role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.agentTeam({ user_input: text });
      /* 中间件兜底拦截：HTTP 400 + code=emergency_signal_detected */
      if (res.status === 400) {
        try {
          const data = await res.json();
          if (data.code === "emergency_signal_detected" || data.code === "extreme_biomarker_value") {
            setMessages((m) => [...m, userMsg]);
            setEmergency({ signal: { category: data.category, keywords: data.keywords }, guidance: data.guidance });
            return;
          }
        } catch {}
        throw new Error("bad request");
      }
      const data = await res.json();
      if (data.messages && Array.isArray(data.messages)) {
        setMessages((m) => [...m, ...data.messages.map((msg) => ({
          role: msg.role || msg.sender || "agent",
          content: msg.content || msg.text || "",
          metadata: msg.metadata || {},
        }))]);
      } else if (data.plan || data.result || data.summary) {
        // team_run may return { plan, result, summary }
        const parts = [];
        if (data.plan) parts.push({ role: "Planner", content: JSON.stringify(data.plan, null, 2) });
        if (data.result) parts.push({ role: "Executor", content: typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2) });
        if (data.summary) parts.push({ role: "Referee", content: data.summary });
        if (parts.length === 0) parts.push({ role: "agent", content: JSON.stringify(data, null, 2) });
        setMessages((m) => [...m, ...parts]);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: JSON.stringify(data, null, 2) }]);
      }
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("agent.agentError") }]);
    }
    setLoading(false);
  }

  function colorForRole(role) {
    const r = ROLES.find((x) => role.includes(x.key));
    return r ? r.color : "#888";
  }

  return (
    <div className="flex flex-col h-full" style={{ height: "calc(100vh - 140px)" }}>
      <h2>🤖 {t("agent.title")}</h2>
      <p style={{ color: "#888", marginBottom: "12px" }}>
        {t("agent.subtitle")}
      </p>

      <div className="flex-1 overflow-y-auto border rounded-lg p-4 mb-3" style={{ maxHeight: "500px" }}>
        {messages.length === 0 && !emergency && (
          <p style={{ color: "#aaa", textAlign: "center", padding: "40px 0" }}>
            {t("agent.emptyHint")}
          </p>
        )}
        {messages.map((m, i) => {
          const isUser = m.role === "user";
          const color = isUser ? "#6366f1" : colorForRole(m.role);
          return (
            <div key={i} className={`mb-3 ${isUser ? "text-right" : "text-left"}`}>
              <div
                className="inline-block px-3 py-2 rounded-lg"
                style={{
                  background: isUser ? "#eef2ff" : "#f9fafb",
                  border: `1px solid ${color}`,
                  maxWidth: "75%",
                  color: "#1f2937",
                }}
              >
                <div style={{ fontSize: "11px", color, fontWeight: "bold", marginBottom: "4px" }}>
                  {isUser ? t("agent.you") : (m.role || "Agent")}
                </div>
                <div style={{ fontSize: "13px", lineHeight: "1.5" }}>{m.content}</div>
              </div>
            </div>
          );
        })}
        {loading && (
          <div className="text-left mb-3">
            <div className="inline-block px-3 py-2 rounded-lg bg-gray-50 border border-gray-200" style={{ color: "#6b7280", fontSize: "13px" }}>
              {t("agent.thinking")}
            </div>
          </div>
        )}
      </div>

      {/* ---- 急救强提示：命中紧急信号时置顶渲染，红色警示不可忽略 ---- */}
      {emergency && (
        <div style={EMERGENCY_STYLE}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
            <div style={{ fontSize: "24px", lineHeight: "1" }}>🚨</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: "bold", color: "#dc2626", fontSize: "15px", marginBottom: "8px" }}>
                {t("agent.emergency.title")}
                {emergency.signal && emergency.signal.category
                  ? ` · ${t("agent.emergency.category")}${emergency.signal.category}`
                  : ""}
              </div>
              <div
                style={{
                  fontSize: "13px",
                  lineHeight: "1.7",
                  color: "#374151",
                  whiteSpace: "pre-wrap",
                }}
              >
                {emergency.guidance || t("agent.emergency.fallback")}
              </div>
              {emergency.signal && emergency.signal.keywords && emergency.signal.keywords.length > 0 && (
                <div style={{ marginTop: "8px", fontSize: "11px", color: "#991b1b" }}>
                  {t("agent.emergency.matched")}: {emergency.signal.keywords.join("、")}
                </div>
              )}
              <div style={{ marginTop: "10px" }}>
                <button
                  onClick={() => setEmergency(null)}
                  className="px-3 py-1 text-xs rounded"
                  style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}
                >
                  {t("agent.emergency.close")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <input
          className="flex-1 border rounded-lg px-4 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={t("agent.placeholder")}
        />
        <button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50" onClick={send} disabled={loading}>
          {t("agent.sendBtn")}
        </button>
      </div>

      <div className="mt-3 flex gap-2 flex-wrap">
        {ROLES.map((r) => (
          <span key={r.key} className="px-2 py-1 rounded text-xs" style={{ background: r.color + "22", color: r.color, border: `1px solid ${r.color}` }}>
            {r.key}: {t(r.labelKey)}
          </span>
        ))}
      </div>
    </div>
  );
}
