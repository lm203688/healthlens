/** AI 对话 — 四角色 Agent 团队 */
import { useState } from "react";
import { api } from "../api/client";

const ROLES = [
  { key: "Planner", color: "#6366f1", label: "规划师" },
  { key: "Executor", color: "#10b981", label: "执行者" },
  { key: "Critic", color: "#f59e0b", label: "批评者" },
  { key: "Referee", color: "#ef4444", label: "仲裁者" },
];

export default function AgentChat() {
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
        // team_run 返回的格式可能是 { plan, result, summary }
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
      setMessages((m) => [...m, { role: "assistant", content: "Agent 服务暂不可用，请刷新重试。" }]);
    }
    setLoading(false);
  }

  function colorForRole(role) {
    const r = ROLES.find((x) => role.includes(x.key));
    return r ? r.color : "#888";
  }

  return (
    <div className="flex flex-col h-full" style={{ height: "calc(100vh - 140px)" }}>
      <h2>🤖 AI 健康顾问</h2>
      <p style={{ color: "#888", marginBottom: "12px" }}>
        四角色 Agent 团队协作（Planner → Executor → Critic → Referee）
      </p>

      <div className="flex-1 overflow-y-auto border rounded-lg p-4 mb-3" style={{ maxHeight: "500px" }}>
        {messages.length === 0 && (
          <p style={{ color: "#aaa", textAlign: "center", padding: "40px 0" }}>
            输入您的症状或健康问题，AI 团队将为您分析
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
                  {isUser ? "您" : (m.role || "Agent")}
                </div>
                <div style={{ fontSize: "13px", lineHeight: "1.5" }}>{m.content}</div>
              </div>
            </div>
          );
        })}
        {loading && (
          <div className="text-left mb-3">
            <div className="inline-block px-3 py-2 rounded-lg bg-gray-50 border border-gray-200" style={{ color: "#6b7280", fontSize: "13px" }}>
              ⏳ Agent 团队思考中...
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
          placeholder="描述您的症状，例如：最近容易疲劳、怕冷..."
        />
        <button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50" onClick={send} disabled={loading}>
          发送
        </button>
      </div>

      <div className="mt-3 flex gap-2 flex-wrap">
        {ROLES.map((r) => (
          <span key={r.key} className="px-2 py-1 rounded text-xs" style={{ background: r.color + "22", color: r.color, border: `1px solid ${r.color}` }}>
            {r.key}: {r.label}
          </span>
        ))}
      </div>
    </div>
  );
}