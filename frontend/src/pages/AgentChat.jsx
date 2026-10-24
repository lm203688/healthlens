/** AI Chat — Four-role Agent team */
import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { track } from "../lib/track";
import { MessageContent } from "../lib/markdown";
import {
  loadHistory,
  appendMessage,
  clearHistory,
  buildContext,
} from "../lib/chatStore";

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

// P0-3b（2026-10-24）：SSE 事件分发——把 plan / result / summary 按阶段推入消息列表
function parseSSE(raw) {
  const lines = raw.split("\n");
  let event = null, data = null;
  for (const line of lines) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data = line.slice(6).trim();
  }
  if (!event || !data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: { raw: data } };
  }
}

function pushMessage(list, msg) {
  return [...list, msg];
}

export default function AgentChat() {
  const { t } = useTranslation();
  // P0-3a（2026-10-24）：初始化时从 localStorage 恢复历史，避免每次刷新都冷启动
  const [messages, setMessages] = useState(() => loadHistory());
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // 急救拦截状态：null | { signal, guidance }
  const [emergency, setEmergency] = useState(null);
  const scrollRef = useRef(null);

  // 新消息到达时自动滚到底
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  function handleClear() {
    if (!confirm(t("agent.confirmClear"))) return;
    clearHistory();
    setMessages([]);
    setEmergency(null);
  }

  // P0-3b：SSE 事件处理器。把每个 event 转换成一条消息推入列表。
  // 关键点：多次 setMessages 会用最新值，所以用函数式更新。
  function handleSSEEvent(evt) {
    if (evt.event === "meta") {
      // 静默，不显示
      return;
    }
    if (evt.event === "plan") {
      const d = evt.data;
      const axes = (d.axes || []).join(", ") || "—";
      const hints = (d.pathway_hints || []).join(", ") || "—";
      const msg = {
        role: "Planner",
        content: `**计划**\n- 目标轴：${axes}\n- 通路提示：${hints}\n- 需要基因：${d.needs_gene ? "是" : "否"}`,
      };
      setMessages((m) => pushMessage(m, msg));
      appendMessage(msg);
      return;
    }
    if (evt.event === "result") {
      const d = evt.data;
      const recs = Array.isArray(d.recommendations) ? d.recommendations : [];
      const summary = recs.slice(0, 3).map((r) =>
        `- ${r.prescription || r.targeted_pathway || r.case_id}`
      ).join("\n");
      const msg = {
        role: "Executor",
        content: `**执行结果**（共 ${recs.length} 条建议）\n${summary || "（无）"}`,
      };
      setMessages((m) => pushMessage(m, msg));
      appendMessage(msg);
      return;
    }
    if (evt.event === "summary") {
      const d = evt.data;
      const msg = { role: "Referee", content: `**评审**\n${d.summary || "（无）"}` };
      setMessages((m) => pushMessage(m, msg));
      appendMessage(msg);
      return;
    }
    if (evt.event === "error") {
      const msg = { role: "assistant", content: `⚠️ ${evt.data?.message || "unknown error"}` };
      setMessages((m) => pushMessage(m, msg));
      appendMessage(msg);
      return;
    }
    // done 事件：什么都不做（loading 已在流式循环后设置 false）
  }

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
    appendMessage(userMsg);                 // 持久化到 localStorage
    setInput("");
    setLoading(true);
    // P0-4（2026-10-23）：埋点——agent_message_sent
    try { track("agent_message_sent", { chars: text.length }); } catch {}

    // P0-3a（2026-10-24）：多轮上下文——把最近几条一起发给后端，避免每轮都失忆
    const context = buildContext();
    const payload = {
      user_input: text,
      history: context,   // [{role, content}] 最近 6 条
    };

    // P0-3b（2026-10-24）：优先走 SSE 流式，让前端分阶段收到 plan / result / summary
    try {
      const sseRes = await api.agentTeamStream(payload);
      if (sseRes.ok && sseRes.headers.get('content-type')?.includes('text/event-stream')) {
        // 流式消费 SSE 事件，边生成边渲染
        const reader = sseRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let gotAny = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE 事件以 \n\n 分隔
          let sep;
          while ((sep = buffer.indexOf("\n\n")) !== -1) {
            const raw = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const evt = parseSSE(raw);
            if (!evt) continue;
            gotAny = true;
            handleSSEEvent(evt);
          }
        }
        // 全部流式事件已消费
        if (gotAny) return;
      }
    } catch {
      // SSE 失败 → 静默降级到非流式
    }

    // 非流式 fallback（原有路径）
    try {
      const res = await api.agentTeam(payload);
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
        const parsed = data.messages.map((msg) => ({
          role: msg.role || msg.sender || "agent",
          content: msg.content || msg.text || "",
          metadata: msg.metadata || {},
        }));
        setMessages((m) => [...m, ...parsed]);
        // 持久化：每条单独 append，保留 ts
        parsed.forEach(appendMessage);
      } else if (data.plan || data.result || data.summary) {
        // P0-3（2026-10-23）：修 U3——原来直接 JSON.stringify(plan) 让用户看到裸 JSON 与
        // {"axes":["A"]}。改为把四角色输出转成"过程卡片"文本：标题 + 关键事实行，
        // 用户能看到"计划→执行→评审→裁定"的真实工作流而不是 JSON 字面量。
        const parts = [];
        if (data.plan) {
          const axes = (data.plan.axes || []).join(", ") || "—";
          const hints = (data.plan.pathway_hints || []).join(", ") || "—";
          parts.push({
            role: "Planner",
            content: `**计划**\n- 目标轴：${axes}\n- 通路提示：${hints}\n- 需要基因：${data.plan.needs_gene ? "是" : "否"}`,
          });
        }
        if (data.result) {
          const recs = Array.isArray(data.result.recommendations)
            ? data.result.recommendations
            : [];
          const summary = recs.slice(0, 3).map((r) =>
            `- ${r.prescription || r.targeted_pathway || r.case_id}`
          ).join("\n");
          parts.push({
            role: "Executor",
            content: `**执行结果**（共 ${recs.length} 条建议）\n${summary || typeof data.result === 'string' ? data.result : "（无）"}`,
          });
        }
        if (data.summary) {
          parts.push({ role: "Referee", content: `**评审**\n${data.summary}` });
        }
        if (parts.length === 0) {
          parts.push({ role: "assistant", content: JSON.stringify(data, null, 2) });
        }
        setMessages((m) => [...m, ...parts]);
        parts.forEach(appendMessage);
      } else {
        const fallback = { role: "assistant", content: JSON.stringify(data, null, 2) };
        setMessages((m) => [...m, fallback]);
        appendMessage(fallback);
      }
    } catch {
      const err = { role: "assistant", content: t("agent.agentError") };
      setMessages((m) => [...m, err]);
      appendMessage(err);
    }
    setLoading(false);
  }

  function colorForRole(role) {
    const r = ROLES.find((x) => role.includes(x.key));
    return r ? r.color : "#888";
  }

  return (
    <div className="flex flex-col h-full" style={{ height: "calc(100vh - 140px)" }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ margin: 0 }}>🤖 {t("agent.title")}</h2>
          <p style={{ color: "#888", marginBottom: "12px", marginTop: '4px' }}>
            {t("agent.subtitle")}
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={handleClear}
            className="px-3 py-1 text-xs rounded"
            style={{ background: "#f3f4f6", color: "#4b5563", border: "1px solid #d1d5db" }}
            title={t("agent.clearHint")}
          >
            🗑 {t("agent.clearBtn")}
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto border rounded-lg p-4 mb-3" style={{ maxHeight: "500px" }}>
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
                {/* P0-3a：Markdown 渲染，支持 **加粗** / `代码` / - 列表 / ```代码块``` */}
                <MessageContent content={m.content} />
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
