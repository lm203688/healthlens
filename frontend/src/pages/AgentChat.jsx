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

export default function AgentChat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    if (!input.trim() || loading) return;
    const userMsg = { role: "user", content: input.trim() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.agentTeam({ user_input: userMsg.content });
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
        {messages.length === 0 && (
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
