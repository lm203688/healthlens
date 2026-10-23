/* P0-4（2026-10-23）：前端埋点封装。
 *
 * 背景：2026-10-22 产品评估定位到"后端 analytics 四件套齐全，前端零调用"——
 * 无法量化首日完成评估率、D7 留存、周报打开率等北极星指标。此模块封装 12 个
 * 核心事件，接入现有 /analytics/event 端点，事件名与语义保持稳定，供后续
 * dashboard / A-B 实验消费。
 *
 * 事件清单（12 个）：
 *   user_registered               注册成功
 *   assessment_started            问卷开始
 *   assessment_question_answered  每题作答（含 question_index）
 *   assessment_completed          问卷完成
 *   assessment_submitted          评估提交（→ Agent 融合）
 *   result_viewed                 结果页查看
 *   recommendation_clicked        建议卡片点击
 *   device_connect_attempted      设备连接尝试
 *   file_uploaded                 文件上传（化验单/基因组）
 *   daily_checkin                 每日打卡
 *   payment_clicked               支付按钮点击
 *   share_clicked                 分享按钮点击
 *
 * 埋点失败不阻断主流程：静默 catch。生产环境建议加采样率；本地开发可全量。
 */
import { api } from "../api/client";

const SESSION_ID = (() => {
  let sid = sessionStorage.getItem("hl_session_id");
  if (!sid) {
    sid = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem("hl_session_id", sid);
  }
  return sid;
})();

// 12 个核心事件的白名单——防止误埋点污染 dashboard
const ALLOWED_EVENTS = new Set([
  "user_registered",
  "assessment_started",
  "assessment_question_answered",
  "assessment_completed",
  "assessment_submitted",
  "result_viewed",
  "recommendation_clicked",
  "device_connect_attempted",
  "file_uploaded",
  "daily_checkin",
  "payment_clicked",
  "share_clicked",
]);

/**
 * 埋点上报。fire-and-forget，失败静默。
 * @param {string} event 事件名（在 ALLOWED_EVENTS 白名单内）
 * @param {object} [props] 事件属性
 */
export async function track(event, props = {}) {
  if (!ALLOWED_EVENTS.has(event)) return;
  try {
    const body = {
      event,
      session_id: SESSION_ID,
      user_id: localStorage.getItem("user_id") || null,
      timestamp: new Date().toISOString(),
      page: window.location.pathname.replace(/^\/app\//, ""),
      url: window.location.href,
      ...props,
    };
    await api.analyticsEvent(body);
  } catch {
    /* 埋点失败不阻断主流程 */
  }
}

/** 获取当前会话 id（供跨模块关联用） */
export function getSessionId() {
  return SESSION_ID;
}
