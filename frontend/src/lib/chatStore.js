/* 会话持久化存储（localStorage）
 *
 * 背景：AgentChat 每次刷新或路由跳转都从零开始，用户丢上下文。
 * 此模块把消息历史按 session_id 分区存 localStorage，支持：
 *   - 页面刷新恢复
 *   - 多轮上下文窗口（发送时自动携带最近 N 条）
 *   - 手动清空会话
 *   - 会话数量上限（防 localStorage 爆掉）
 *
 * 存储结构：
 *   hl_chat_history_v1 = {
 *     "<session_id>": {
 *       createdAt: ISO,
 *       updatedAt: ISO,
 *       messages: [{role, content, metadata, ts}, ...]
 *     }
 *   }
 */

const STORE_KEY = 'hl_chat_history_v1';
const MAX_SESSIONS = 10;
const MAX_MESSAGES_PER_SESSION = 100;
const LOAD_WINDOW = 50;       // 页面加载时最多恢复多少条
const CONTEXT_WINDOW = 6;     // 每次请求发送最近多少条作为上下文

function readStore() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
  } catch {
    return {};
  }
}

function writeStore(store) {
  // 会话数量裁剪：按 updatedAt 排序，保留最新 MAX_SESSIONS 个
  const sorted = Object.entries(store)
    .sort((a, b) => (b[1].updatedAt || '').localeCompare(a[1].updatedAt || ''));
  const trimmed = Object.fromEntries(sorted.slice(0, MAX_SESSIONS));
  localStorage.setItem(STORE_KEY, JSON.stringify(trimmed));
}

function getSessionId() {
  let sid = sessionStorage.getItem('hl_session_id');
  if (!sid) {
    sid = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem('hl_session_id', sid);
  }
  return sid;
}

/** 加载某会话的消息历史（默认当前会话） */
export function loadHistory(sessionId = getSessionId()) {
  const store = readStore();
  const session = store[sessionId];
  if (!session) return [];
  return (session.messages || []).slice(-LOAD_WINDOW);
}

/** 追加消息到当前会话 */
export function appendMessage(msg, sessionId = getSessionId()) {
  const store = readStore();
  const now = new Date().toISOString();
  if (!store[sessionId]) {
    store[sessionId] = { createdAt: now, updatedAt: now, messages: [] };
  }
  store[sessionId].messages.push({ ...msg, ts: now });
  // 消息数上限：超出裁掉最旧
  if (store[sessionId].messages.length > MAX_MESSAGES_PER_SESSION) {
    store[sessionId].messages = store[sessionId].messages.slice(-MAX_MESSAGES_PER_SESSION);
  }
  store[sessionId].updatedAt = now;
  writeStore(store);
}

/** 清空当前会话历史 */
export function clearHistory(sessionId = getSessionId()) {
  const store = readStore();
  delete store[sessionId];
  writeStore(store);
}

/** 生成多轮上下文 payload：最近 CONTEXT_WINDOW 条转成 [{role, content}] */
export function buildContext(sessionId = getSessionId()) {
  const all = loadHistory(sessionId);
  const window = all.slice(-CONTEXT_WINDOW);
  return window.map(m => ({ role: m.role, content: m.content }));
}

/** 列出所有会话摘要（供未来"会话列表" UI 用） */
export function listSessions() {
  const store = readStore();
  return Object.entries(store)
    .map(([id, s]) => ({
      id,
      updatedAt: s.updatedAt,
      createdAt: s.createdAt,
      messageCount: (s.messages || []).length,
      preview: (s.messages || []).slice(-1)[0]?.content?.slice(0, 60) || '',
    }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}
