/* API 客户端 — 与后端 FastAPI 服务通信 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

async function request(path, options = {}) {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (resp.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  }
  return resp;
}

export const api = {
  /* ===== 认证 ===== */
  login:    (body) => request('/auth/login',    { method: 'POST', body: JSON.stringify(body) }),
  register: (body) => request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  refresh:  (body) => request('/auth/refresh',  { method: 'POST', body: JSON.stringify(body) }),
  me:       ()    => request('/auth/me'),

  /* ===== 健康评估（Agent 融合管线）===== */
  agentFusion: (body) => request('/agent/fusion', { method: 'POST', body: JSON.stringify(body) }),
  agentTeam:   (body) => request('/agent/team',   { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 体质分析（TCM）===== */
  tcmConstitution:   () => request('/tcm/constitution'),
  tcmConstitutionPost: (body) => request('/tcm/constitution', { method: 'POST', body: JSON.stringify(body) }),
  tcmSyndrome:       (body) => request('/tcm/syndrome', { method: 'POST', body: JSON.stringify(body) }),
  tcmDiagnose:       (body) => request('/tcm/diagnose', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 健康报告 ===== */
  reports: () => request('/reports/health'),

  /* ===== 知识库 ===== */
  knowledgeSearch: (query) => request(`/knowledge/search?q=${encodeURIComponent(query)}`),
  knowledgeFood:   (query) => request(`/knowledge/food?q=${encodeURIComponent(query)}`),
  knowledgeMethods:(query) => request(`/knowledge/non-drug?q=${encodeURIComponent(query)}`),

  /* ===== 健康仪表盘 ===== */
  dashboard: () => request('/dashboard/overview'),

  /* ===== 慢病风险评估 ===== */
  riskAsc: (body) => request('/diagnosis/risk/ascvd', { method: 'POST', body: JSON.stringify(body) }),

  /* ===== 健康档案 ===== */
  profiles: () => request('/profiles'),
  profile:  (id) => request(`/profiles/${id}`),

  /* ===== 每日健康打卡（observations）===== */
  observations: () => request('/observations'),
  observationPost: (body) => request('/observations', { method: 'POST', body: JSON.stringify(body) }),
  observationsBatch: (body) => request('/observations/batch', { method: 'POST', body: JSON.stringify(body) }),
  observationTrend: () => request('/observations/trend'),
  observationSummary: () => request('/observations/summary'),
};
