/* API 客户端 — 与后端 FastAPI 服务通信 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';
export function apiBase() { return API_BASE; }

// SPA 部署在 /app/ 子路径下（见 vite.config.js base），登录页是 /app/login 而非 /login。
// 写死 '/login' 会跳到域名根的 GEO 首页，用户会以为"退出后跑到别的地方去了"。
const APP_BASE = import.meta.env.BASE_URL || '/app/';

async function request(path, options = {}) {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (resp.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    window.location.href = `${APP_BASE}login`;
  }
  return resp;
}

export const api = {
  /* ===== 认证 ===== */
  login:    (body) => request('/auth/login',    { method: 'POST', body: JSON.stringify(body) }),
  register: (body) => request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  refresh:  (body) => request('/auth/refresh',  { method: 'POST', body: JSON.stringify(body) }),
  me:       ()    => request('/auth/me'),

  /* ===== 验证码登录（登录与注册合一）===== */
  otpSend:   (body) => request('/auth/otp/send',   { method: 'POST', body: JSON.stringify(body) }),
  otpVerify: (body) => request('/auth/otp/verify', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== TOTP 验证器 App 通道 =====
   * enroll/disable 无需请求体；verify/confirm 传 { code }；method 传 { method: 'otp'|'totp' }
   * 登录（verify）为未鉴权端点：仅 6 位码即可登录已绑定用户。
   * 绑定（enroll/confirm/disable/method）需先登录，故放在个人档案页。 */
  totpStatus:  ()     => request('/auth/totp/status'),
  totpEnroll:  ()     => request('/auth/totp/enroll',  { method: 'POST' }),
  totpVerify:  (body) => request('/auth/totp/verify',  { method: 'POST', body: JSON.stringify(body) }),
  totpConfirm: (body) => request('/auth/totp/confirm', { method: 'POST', body: JSON.stringify(body) }),
  totpDisable: ()     => request('/auth/totp/disable', { method: 'POST' }),
  totpMethod:  (body) => request('/auth/totp/method',  { method: 'PUT',  body: JSON.stringify(body) }),

  /* ===== 法域/合规设置 ===== */
  updateJurisdiction: (body) => request('/auth/jurisdiction', { method: 'PUT', body: JSON.stringify(body) }),

  /* ===== 健康评估（Agent 融合管线）===== */
  agentFusion: (body) => request('/agent/fusion', { method: 'POST', body: JSON.stringify(body) }),
  agentTeam:   (body) => request('/agent/team',   { method: 'POST', body: JSON.stringify(body) }),
  // P0-3b（2026-10-24）：SSE 流式版本，用 fetch + ReadableStream 消费（不用 EventSource 因为需要 POST body）
  agentTeamStream: (body) => fetch(`${API_BASE}/agent/team/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),

  /* ===== 健康护栏预检（提交自由文本前调用，命中即强提示就医）===== */
  emergencyCheck: (text) => request('/emergency/check', { method: 'POST', body: JSON.stringify({ text }) }),

  /* ===== 体质分析（TCM）===== */
  tcmConstitution:   () => request('/tcm/constitution'),
  tcmConstitutionPost: (body) => request('/tcm/constitution', { method: 'POST', body: JSON.stringify(body) }),
  tcmSyndrome:       (body) => request('/tcm/syndrome', { method: 'POST', body: JSON.stringify(body) }),
  tcmDiagnose:       (body) => request('/tcm/diagnose', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 号脉解读 =====
   * interpret 直传一组成熟特征（即时解读，硬件/演示都可）；
   * byUser 按 user_ref 拉边缘盒最近上报（需登录态）。 */
  pulseInterpret:  (body) => request('/pulse/interpret', { method: 'POST', body: JSON.stringify(body) }),
  pulseByUser:     (body) => request('/agent/pulse', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 健康报告 ===== */
  reports: () => request('/reports/health'),

  /* ===== 知识库 ===== */
  knowledgeSearch: (query) => request(`/knowledge/search?q=${encodeURIComponent(query)}`),
  knowledgeFood:   (query) => request(`/knowledge/food?q=${encodeURIComponent(query)}`),
  knowledgeMethods:(query) => request(`/knowledge/non-drug?q=${encodeURIComponent(query)}`),

  /* ===== 健康仪表盘 ===== */
  dashboard: () => request('/dashboard/overview'),

  /* ===== 支付与会员 ===== */
  paymentFeatures: () => request('/payment/features'),
  paymentCreate: (body) => request('/payment/create', { method: 'POST', body: JSON.stringify(body) }),
  paymentStatus: (orderNo) => request(`/payment/status/${orderNo}`),
  paymentBalance: () => request('/points/balance'),
  freemiumFeatures: () => request('/freemium/features'),
  freemiumBalanceInfo: () => request('/freemium/balance-info'),
  freemiumCheck: (featureCode) => request(`/freemium/check?feature_code=${featureCode}`),

  /* ===== 基因组上传 ===== */
  genomeUpload: (formData) => fetch(`${API_BASE}/genome/upload`, { method: 'POST', body: formData }),
  genomeProfile: () => request('/genome/profile'),
  genomePgx: () => request('/genome/pgx'),

  /* ===== 报告分享 ===== */
  reportShare: (body) => request('/reports/share', { method: 'POST', body: JSON.stringify(body) }),
  myShares: (page) => request(`/reports/my-shares?page=${page || 1}`),
  revokeShare: (reportId) => request(`/reports/${reportId}/revoke`, { method: 'POST' }),

  /* ===== 慢病风险评估 ===== */
  riskAsc: (body) => request('/diagnosis/risk/ascvd', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 健康档案 ===== */
  profiles: () => request('/profiles'),
  profile:  (id) => request(`/profiles/${id}`),

  /* ===== 八轴稳态（代谢-炎症轴 / PhenoAge 借鉴）===== */
  axesMeta:   ()     => request('/axes/meta'),
  axesBioage: (body) => request('/axes/bioage', { method: 'POST', body: JSON.stringify(body) }),
  axesAssess: (body) => request('/axes/assess', { method: 'POST', body: JSON.stringify(body) }),
  axesProject: (body) => request('/axes/project', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 数据连接（可穿戴设备）===== */
  connections: () => request('/connections/'),

  /* ===== wellness 自测闭环（SIIV V 端：能量/消化/睡眠 1-5）===== */
  checkinPost:    (body) => request('/checkin',        { method: 'POST', body: JSON.stringify(body) }),
  checkinHistory: ()     => request('/checkin/history'),
  checkinSummary: ()     => request('/checkin/summary'),

  /* ===== 留存闭环：健康目标 ===== */
  goalsList:    ()         => request('/goals'),
  goalCreate:   (body)     => request('/goals', { method: 'POST', body: JSON.stringify(body) }),
  goalDetail:   (id)       => request(`/goals/${id}`),
  goalUpdate:   (id, body) => request(`/goals/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  goalDelete:   (id)       => request(`/goals/${id}`, { method: 'DELETE' }),
  goalProgress: (id, body) => request(`/goals/${id}/progress`, { method: 'POST', body: JSON.stringify(body) }),
  goalsStats:   ()         => request('/goals/summary/stats'),

  /* ===== 留存闭环：通知中心 ===== */
  notifications:      (unreadOnly) => request(`/notifications?page_size=50${unreadOnly ? '&is_read=false' : ''}`),
  notificationsUnread:()   => request('/notifications/unread/count'),
  notificationRead:   (id) => request(`/notifications/${id}/read`, { method: 'PUT' }),
  notificationsReadAll:()  => request('/notifications/read-all', { method: 'PUT' }),
  notificationDelete: (id) => request(`/notifications/${id}`, { method: 'DELETE' }),

  /* ===== 留存闭环：依从追踪 ===== */
  adherenceList:  ()         => request('/adherence'),
  adherenceCreate:(body)     => request('/adherence', { method: 'POST', body: JSON.stringify(body) }),
  adherenceUpdate:(id, body) => request(`/adherence/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  adherenceStats: ()         => request('/adherence/stats/summary'),

  /* ===== 每日健康打卡（observations）===== */
  observations: () => request('/observations'),
  observationPost: (body) => request('/observations', { method: 'POST', body: JSON.stringify(body) }),
  observationsBatch: (body) => request('/observations/batch', { method: 'POST', body: JSON.stringify(body) }),
  observationTrend: () => request('/observations/trend'),
  observationSummary: () => request('/observations/summary'),

  /* ===== 纵向追踪 / n-of-1 对比（P0-2 可达性打通，2026-10-23）=====
   * 全项目最值钱的闭环："我做了 8 周干预，到底变没变？"
   * 后端已有 10 端点，但 client.js 曾完全未封装，前端零触达。
   */
  longitudinalStudies: () => request('/longitudinal/studies'),
  longitudinalStudy: (id) => request(`/longitudinal/studies/${id}`),
  longitudinalCreateStudy: (body) => request('/longitudinal/studies', { method: 'POST', body: JSON.stringify(body) }),
  longitudinalAddSnapshot: (id, body) => request(`/longitudinal/studies/${id}/snapshots`, { method: 'POST', body: JSON.stringify(body) }),
  longitudinalTrajectory: (id) => request(`/longitudinal/studies/${id}/trajectory`),
  longitudinalAddIntervention: (id, body) => request(`/longitudinal/studies/${id}/interventions`, { method: 'POST', body: JSON.stringify(body) }),
  longitudinalListInterventions: (id) => request(`/longitudinal/studies/${id}/interventions`),
  longitudinalAddReading: (id, body) => request(`/longitudinal/studies/${id}/readings`, { method: 'POST', body: JSON.stringify(body) }),
  longitudinalListReadings: (id) => request(`/longitudinal/studies/${id}/readings`),
  longitudinalComparison: (id, body) => request(`/longitudinal/studies/${id}/comparison`, { method: 'POST', body: JSON.stringify(body) }),
  longitudinalTriggerWeeklyReport: (id, daysBack = 14) => request(`/longitudinal/studies/${id}/weekly-report?days_back=${daysBack}`, { method: 'POST' }),
  longitudinalListWeeklyReports: (daysBack = 60, limit = 10) => request(`/longitudinal/weekly-reports?days_back=${daysBack}&limit=${limit}`),

  /* ===== 因果推断 / DoWhy（P0-2，把"为什么这么建议"讲清楚）===== */
  causalScm: () => request('/causal/scm'),
  causalSensitivity: () => request('/causal/sensitivity'),
  causalLevers: () => request('/causal/levers'),
  causalCounterfactual: (body) => request('/causal/counterfactual', { method: 'POST', body: JSON.stringify(body) }),
  causalCalibrate: (body) => request('/causal/calibrate', { method: 'POST', body: JSON.stringify(body) }),
  causalReport: (body) => request('/causal/report', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 证据库（P0-2，点开建议看 L1/L2/L3 出处）===== */
  evidenceCases: (q) => request(`/evidence/cases${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  evidenceCase: (id) => request(`/evidence/cases/${id}`),

  /* ===== 行为分析 / 埋点（P0-4，前端 12 个核心事件 → analytics/event）===== */
  analyticsEvent: (body) => request('/analytics/event', { method: 'POST', body: JSON.stringify(body) }),
  analyticsSession: (body) => request('/analytics/session', { method: 'POST', body: JSON.stringify(body) }),
  analyticsConversion: (body) => request('/analytics/conversion', { method: 'POST', body: JSON.stringify(body) }),
  analyticsDashboard: () => request('/analytics/dashboard'),
};
