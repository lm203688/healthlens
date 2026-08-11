/**
 * HealthLens Frontend Application
 * Integrated with HealthLens Backend API
 */

(function () {
  'use strict';

  // ==================== Configuration ====================
  const API_BASE = window.API_BASE_OVERRIDE || window.location.origin;  // 同源部署时自动使用当前域名；预览可经 window.API_BASE_OVERRIDE 强制指定

  // LOINC codes for trend metrics
  const LOINC_CODES = {
    glucose: '2345-7',
    pressure: '8480-6',
    weight: '29463-7'
  };

  // ==================== State ====================
  const state = {
    currentUser: null,
    currentPage: 'dashboard',
    trendMetric: 'glucose',
    demoMode: false,
    resultReadOnly: false,   // 演示/不可用结果不可保存/分享（信任护栏）
    resultTrust: null,
    cache: {},
    isRefreshing: false,
    refreshPromise: null,
    selectedRecordId: null,
    constitutionType: null,
    constitutionScores: null
  };

  // ==================== Inject Styles ====================
  const styleEl = document.createElement('style');
  styleEl.textContent = `
    /* Toast Notifications */
    #toast-container {
      position: fixed; bottom: 20px; right: 20px; z-index: 10000;
      display: flex; flex-direction: column-reverse; gap: 8px;
      pointer-events: none;
    }
    .toast {
      pointer-events: auto;
      display: flex; align-items: center; gap: 10px;
      padding: 12px 16px; border-radius: 10px; color: #fff;
      font-size: 14px; min-width: 280px; max-width: 420px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.18);
      animation: toast-slide-in 0.35s cubic-bezier(.21,1.02,.73,1);
      font-family: 'Noto Sans SC', sans-serif; line-height: 1.4;
    }
    .toast-success { background: #0d8a6a; }
    .toast-error { background: #d63031; }
    .toast-info { background: #2d7dd2; }
    .toast-close {
      background: none; border: none; color: rgba(255,255,255,0.8);
      font-size: 20px; cursor: pointer; margin-left: auto; padding: 0 2px; line-height: 1;
    }
    .toast-close:hover { color: #fff; }
    @keyframes toast-slide-in {
      from { transform: translateX(110%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes toast-slide-out {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(110%); opacity: 0; }
    }

    /* Demo Banner */
    #demo-banner {
      position: fixed; top: 0; left: 0; right: 0;
      background: linear-gradient(90deg, #ff9500, #ff6b00);
      color: #fff; text-align: center; padding: 10px 16px;
      font-size: 14px; z-index: 10001; font-weight: 500;
      cursor: pointer; letter-spacing: 0.5px;
      box-shadow: 0 2px 8px rgba(255,149,0,0.3);
      transition: background 0.2s;
    }
    #demo-banner:hover { background: linear-gradient(90deg, #ff8000, #ff5500); }
    #demo-banner.hidden { display: none; }

    /* Skeleton Loading */
    .skeleton {
      background: linear-gradient(90deg, var(--rule-light) 25%, rgba(255,255,255,0.08) 50%, var(--rule-light) 75%);
      background-size: 200% 100%;
      animation: skeleton-pulse 1.5s ease-in-out infinite;
      border-radius: 6px;
    }
    .skeleton-line { height: 14px; margin-bottom: 10px; }
    .skeleton-line.w60 { width: 60%; }
    .skeleton-line.w80 { width: 80%; }
    .skeleton-line.w40 { width: 40%; }
    .skeleton-card { height: 90px; border-radius: 10px; margin-bottom: 12px; }
    @keyframes skeleton-pulse {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }

    /* Loading Spinner */
    .loading-spinner {
      display: flex; align-items: center; justify-content: center;
      padding: 40px; flex-direction: column; gap: 12px; color: #9ca3af;
    }
    .spinner-ring {
      width: 28px; height: 28px;
      border: 3px solid #e5e7eb; border-top-color: #0d8a6a;
      border-radius: 50%; animation: spin-ring 0.7s linear infinite;
    }
    @keyframes spin-ring { to { transform: rotate(360deg); } }

    /* Empty State */
    .empty-state {
      text-align: center; padding: 48px 20px; color: #9ca3af;
    }
    .empty-state-icon { font-size: 40px; margin-bottom: 12px; }
    .empty-state-text { font-size: 14px; }

    /* Button loading state */
    .btn.loading {
      pointer-events: none; opacity: 0.7; position: relative; color: transparent !important;
    }
    .btn.loading::after {
      content: ''; position: absolute; top: 50%; left: 50%;
      width: 18px; height: 18px; margin: -9px 0 0 -9px;
      border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
      border-radius: 50%; animation: spin-ring 0.6s linear infinite;
    }
  `;
  document.head.appendChild(styleEl);

  // Get or create toast container
  var toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
  }

  // ==================== Toast Notification System ====================
  function showToast(message, type) {
    type = type || 'info';
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML =
      '<span class="toast-message">' + escapeHtml(message) + '</span>' +
      '<button class="toast-close">&times;</button>';
    toastContainer.appendChild(toast);

    var closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', function () {
      toast.style.animation = 'toast-slide-out 0.3s ease forwards';
      setTimeout(function () { toast.remove(); }, 300);
    });

    setTimeout(function () {
      if (toast.parentNode) {
        toast.style.animation = 'toast-slide-out 0.3s ease forwards';
        setTimeout(function () { toast.remove(); }, 300);
      }
    }, 5000);
  }

  // Expose showToast globally for inline HTML handlers
  window.showToast = showToast;
  window.toggleKnowledgeCard = function(el) {
    var answer = el.querySelector('.knowledge-answer');
    var arrow = el.querySelector('.knowledge-arrow');
    if (answer.style.display === 'none') {
      answer.style.display = 'block';
      if (arrow) arrow.style.transform = 'rotate(90deg)';
    } else {
      answer.style.display = 'none';
      if (arrow) arrow.style.transform = 'rotate(0deg)';
    }
  };
  window.filterByTag = function(btn, tag) {
    document.querySelectorAll('.knowledge-tag').forEach(function(t) {
      t.style.background = 'var(--card)';
      t.style.color = 'var(--ink)';
      t.style.borderColor = 'var(--border)';
    });
    btn.style.background = 'var(--accent)';
    btn.style.color = '#fff';
    btn.style.borderColor = 'var(--accent)';
    document.querySelectorAll('.knowledge-card').forEach(function(card) {
      if (tag === 'all') {
        card.style.display = 'block';
      } else {
        var tags = (card.dataset.tags || '').split(',');
        card.style.display = tags.indexOf(tag) !== -1 ? 'block' : 'none';
      }
    });
  };
  window.filterKnowledgeCards = function(keyword) {
    keyword = keyword.toLowerCase().trim();
    document.querySelectorAll('.knowledge-card').forEach(function(card) {
      if (!keyword) {
        card.style.display = 'block';
        return;
      }
      var text = card.textContent.toLowerCase();
      card.style.display = text.indexOf(keyword) !== -1 ? 'block' : 'none';
    });
  };
  window.sendKnowledgeAI = function() {
    var input = document.getElementById('knowledge-ai-input');
    if (input && input.value.trim()) {
      input.value = '';
    }
    window.showToast('AI 咨询功能即将上线', 'info');
  };
  window.triggerAIDiagnosis = triggerAIDiagnosis;
  window.triggerAIPlan = triggerAIPlan;
  window.triggerFrequencyPrescription = triggerFrequencyPrescription;

  function showErrorToast(message) {
    showToast(message, 'error');
  }

  function showSuccessToast(message) {
    showToast(message, 'success');
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ==================== Demo Mode Banner ====================
  function showDemoBanner() {
    state.demoMode = true;
    var existing = document.getElementById('demo-banner');
    if (existing) { existing.classList.remove('hidden'); return; }
    var banner = document.getElementById('demo-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'demo-banner';
      banner.className = 'demo-banner';
      banner.innerHTML = '<span class="demo-banner-icon">&#128161;</span><span>\u6F14\u793A\u6A21\u5F0F \u2014 \u60A8\u6B63\u5728\u4F53\u9A8C HealthLens \u5168\u90E8\u529F\u80FD\uFF0C\u5F53\u524D\u4F7F\u7528\u6A21\u62DF\u6570\u636E\u5C55\u793A</span><span style="font-size:0.75rem;opacity:0.8">(\u70B9\u51FB\u5173\u95ED)</span>';
      banner.title = '\u70B9\u51FB\u5173\u95ED\u63D0\u793A';
      banner.addEventListener('click', function () {
        banner.classList.add('hidden');
      });
      var appViewEl = document.getElementById('app-view');
      if (appViewEl) {
        appViewEl.prepend(banner);
      } else {
        document.body.prepend(banner);
      }
    }
  }

  function hideDemoBanner() {
    var banner = document.getElementById('demo-banner');
    if (banner) banner.remove();
    state.demoMode = false;
  }

  // Initialize after demo mode or login
  setTimeout(function() {
    initTimers();
    initButtonResponses();
  }, 500);

  // ==================== Token Management ====================
  function getAccessToken() {
    return localStorage.getItem('healthlens_access_token');
  }

  function getRefreshToken() {
    return localStorage.getItem('healthlens_refresh_token');
  }

  function saveTokens(accessToken, refreshToken, user) {
    localStorage.setItem('healthlens_access_token', accessToken);
    localStorage.setItem('healthlens_refresh_token', refreshToken);
    if (user) {
      localStorage.setItem('healthlens_user', JSON.stringify(user));
    }
    state.currentUser = user;
  }

  function clearTokens() {
    localStorage.removeItem('healthlens_access_token');
    localStorage.removeItem('healthlens_refresh_token');
    localStorage.removeItem('healthlens_user');
    state.currentUser = null;
  }

  function getStoredUser() {
    try {
      var raw = localStorage.getItem('healthlens_user');
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function isLoggedIn() {
    return !!getAccessToken();
  }

  // ==================== API Helper ====================
  async function refreshToken() {
    if (state.isRefreshing && state.refreshPromise) {
      return state.refreshPromise;
    }
    state.isRefreshing = true;
    state.refreshPromise = (async function () {
      try {
        var rt = getRefreshToken();
        if (!rt) throw new Error('No refresh token');
        var resp = await fetch(API_BASE + '/api/v1/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt })
        });
        if (!resp.ok) throw new Error('Refresh failed');
        var json = await resp.json();
        if (json.success && json.data) {
          saveTokens(json.data.access_token, json.data.refresh_token || rt, json.data.user || state.currentUser);
          return json.data.access_token;
        }
        throw new Error('Invalid refresh response');
      } catch (e) {
        clearTokens();
        showAppropriateView();
        throw e;
      } finally {
        state.isRefreshing = false;
        state.refreshPromise = null;
      }
    })();
    return state.refreshPromise;
  }

  async function api(path, options) {
    if (state.demoMode) {
      return null;
    }
    options = options || {};
    var url = API_BASE + path;
    var headers = options.headers || {};

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    var token = getAccessToken();
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }

    var fetchOptions = {
      method: options.method || 'GET',
      headers: headers
    };
    if (options.body) {
      fetchOptions.body = options.body;
    }

    try {
      var resp = await fetch(url, fetchOptions);

      // Handle 401 - try token refresh
      if (resp.status === 401 && !options._retry) {
        try {
          var newToken = await refreshToken();
          headers['Authorization'] = 'Bearer ' + newToken;
          options._retry = true;
          options.headers = headers;
          return api(path, options);
        } catch (refreshErr) {
          return null;
        }
      }

      var json = await resp.json();

      if (!resp.ok) {
        // 服务器内部错误(500/503)时自动进入演示模式（数据库未连接等）
        if (resp.status >= 500 && resp.status < 600) {
          showDemoBanner();
          return null;
        }
        var errMsg = (json.detail || json.message || json.error || 'Request failed (' + resp.status + ')');
        if (!options.silent) {
          showErrorToast(errMsg);
        }
        return null;
      }

      if (json.success === false) {
        var msg = json.message || json.detail || 'Operation failed';
        if (!options.silent) {
          showErrorToast(msg);
        }
        return null;
      }

      return json.data;
    } catch (err) {
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        // Network error - enter demo mode
        showDemoBanner();
      } else if (!options.silent) {
        showErrorToast(err.message || 'Network error');
      }
      return null;
    }
  }

  // Upload with progress using XMLHttpRequest
  function apiUpload(path, file, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      var formData = new FormData();
      formData.append('file', file);

      var token = getAccessToken();
      xhr.open('POST', API_BASE + path);
      if (token) {
        xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      }

      if (onProgress) {
        xhr.upload.addEventListener('progress', function (e) {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', function () {
        try {
          var json = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300 && json.success !== false) {
            resolve(json.data);
          } else {
            var msg = (json.detail || json.message || 'Upload failed');
            reject(new Error(msg));
          }
        } catch (e) {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', function () {
        showDemoBanner();
        reject(new Error('Network error'));
      });

      xhr.send(formData);
    });
  }

  // ==================== Demo / Fallback Data ====================
  var DEMO = {
    user: { id: 1, name: '\u5F20\u5C0F\u660E', email: 'user@demo.com', role: 'user' },
    dashboard: {
      health_score: 82,
      score_label: '\u826F\u597D',
      score_breakdown: { physiology: 85, lifestyle: 78, chronic_risk: 80 },
      recent_diagnoses: [
        { id: 1, title: '\u7A7A\u8179\u8840\u7CD6\u504F\u9AD8', date: '2026-07-15', department: '\u897F\u533B\u5185\u79D1', status: 'warning', badge: '\u9700\u5173\u6CE8' },
        { id: 2, title: '\u8840\u8102\u8F7B\u5EA6\u5F02\u5E38', date: '2026-07-15', department: '\u897F\u533B\u5185\u79D1', status: 'info', badge: '\u89C2\u5BDF\u4E2D' },
        { id: 3, title: '\u6C14\u865A\u4F53\u8D28\u503E\u5411', date: '2026-07-10', department: '\u4E2D\u533B\u4F53\u8D28\u8FA8\u8BC6', status: 'success', badge: '\u5DF2\u8C03\u7406' }
      ],
      todos: [
        { text: '\u6BCF\u65E5\u6B65\u884C 8000 \u6B65', tag: '\u8FD0\u52A8', done: false },
        { text: '\u670D\u7528\u4E8C\u7532\u53CC\u80CD 500mg', tag: '\u7528\u836F', done: true },
        { text: '\u9EC4\u82AA\u7EA2\u67A3\u8336', tag: '\u98DF\u7597', done: false },
        { text: '\u8DB3\u4E09\u91CC\u7A74\u4F4D\u6309\u6469', tag: '\u4E2D\u533B', done: false }
      ],
      constitution_summary: {
        primary: '\u6C14\u865A\u8D28',
        match_score: 72,
        secondary: ['\u9633\u865A\u8D28(45%)', '\u75F0\u6E7F\u8D28(38%)']
      }
    },
    trend: {
      glucose: {
        label: '\u7A7A\u8179\u8840\u7CD6 (mmol/L)',
        values: [5.8, 6.0, 5.9, 6.2, 6.5, 6.8, 6.6],
        dates: ['07-09', '07-10', '07-11', '07-12', '07-13', '07-14', '07-15'],
        color: '#ff9500',
        reference: 6.1
      },
      pressure: {
        label: '\u6536\u7F29\u538B (mmHg)',
        values: [118, 122, 125, 128, 126, 130, 128],
        dates: ['07-09', '07-10', '07-11', '07-12', '07-13', '07-14', '07-15'],
        color: '#007aff',
        reference: 140
      },
      weight: {
        label: '\u4F53\u91CD (kg)',
        values: [72.5, 72.3, 72.0, 71.8, 71.5, 71.3, 71.0],
        dates: ['07-09', '07-10', '07-11', '07-12', '07-13', '07-14', '07-15'],
        color: '#0d8a6a',
        reference: null
      }
    },
    constitution: {
      constitution_type: '\u6C14\u865A\u8D28',
      match_score: 72,
      constitution_scores: {
        '\u5E73\u548C\u8D28': 55, '\u6C14\u865A\u8D28': 72, '\u9633\u865A\u8D28': 45,
        '\u9634\u865A\u8D28': 30, '\u75F0\u6E7F\u8D28': 38, '\u6E7F\u70ED\u8D28': 25,
        '\u8840\u7600\u8D28': 20, '\u6C14\u90C1\u8D28': 35, '\u7279\u79C0\u8D28': 15
      },
      secondary_types: ['\u9633\u865A\u8D28(45%)', '\u75F0\u6E7F\u8D28(38%)'],
      advice: {
        symptoms: ['\u5BB9\u6613\u75B2\u52B3\uFF0C\u6C14\u77ED\u61D2\u8A00', '\u6613\u51FA\u6C57\uFF0C\u5C24\u5176\u6D3B\u52A8\u540E', '\u62B5\u6297\u529B\u8F83\u5F31\uFF0C\u6613\u611F\u5192', '\u9762\u8272\u504F\u767D\u6216\u840E\u9EC4'],
        diet: ['\u5B9C: \u5C71\u836F\u3001\u7EA2\u67A3\u3001\u9EC4\u82AA\u3001\u5C0F\u7C73', '\u5B9C: \u9E21\u8089\u3001\u725B\u8089\u3001\u9CA4\u9C7C', '\u5FCC: \u751F\u51B7\u3001\u6CB9\u817B\u3001\u8F9B\u8FA3', '\u63A8\u8350: \u9EC4\u82AA\u7EA2\u67A3\u8336\u3001\u5C71\u836F\u7CA5'],
        lifestyle: ['\u907F\u514D\u8FC7\u5EA6\u52B3\u7D2F\u548C\u71AC\u591C', '\u9009\u62E9\u6E29\u548C\u8FD0\u52A8\uFF1A\u592A\u6781\u62F3\u3001\u6563\u6B65', '\u6CE8\u610F\u4FDD\u6696\uFF0C\u5C24\u5176\u8179\u90E8', '\u827E\u7078\u8DB3\u4E09\u91CC\u3001\u6C14\u6D77\u7A74'],
        emotional: ['\u4FDD\u6301\u5FC3\u60C5\u8212\u7545\uFF0C\u5C11\u601D\u8651', '\u907F\u514D\u8FC7\u5EA6\u7D27\u5F20\u548C\u7126\u8651', '\u57F9\u517B\u5174\u8DA3\u7231\u597D', '\u591A\u4E0E\u4EBA\u4EA4\u6D41\uFF0C\u907F\u514D\u5B64\u50FB']
      }
    },
    records: [
      {
        id: 1, title: '\u5E74\u5EA6\u4F53\u68C0\u62A5\u544A', report_date: '2026-07-15',
        status: 'parsed', file_size: 1048576, tags: ['\u8840\u5E38\u89C4', '\u751F\u5316'],
        indicators: [
          { name: '\u7A7A\u8179\u8840\u7CD6', value: '6.8', unit: 'mmol/L', ref: '3.9-6.1', status: 'abnormal', trend: '\u2191 \u504F\u9AD8' },
          { name: '\u603B\u80C6\u56FA\u9187', value: '5.6', unit: 'mmol/L', ref: '3.0-5.2', status: 'abnormal', trend: '\u2191 \u504F\u9AD8' },
          { name: '\u8840\u7EA2\u86CB\u767D', value: '140', unit: 'g/L', ref: '130-175', status: 'normal', trend: '\u6B63\u5E38' },
          { name: '\u767D\u7EC6\u80DE', value: '6.2', unit: '10^9/L', ref: '4.0-10.0', status: 'normal', trend: '\u6B63\u5E38' },
          { name: '\u8840\u538B', value: '128/82', unit: 'mmHg', ref: '<140/90', status: 'normal', trend: '\u6B63\u5E38\u9AD8\u503C' },
          { name: 'BMI', value: '24.2', unit: 'kg/m2', ref: '18.5-24.9', status: 'normal', trend: '\u6B63\u5E38' }
        ]
      },
      {
        id: 2, title: '\u5165\u804C\u4F53\u68C0', report_date: '2026-04-20',
        status: 'parsed', file_size: 524288, tags: ['\u5E38\u89C4'],
        indicators: [
          { name: '\u7A7A\u8179\u8840\u7CD6', value: '5.9', unit: 'mmol/L', ref: '3.9-6.1', status: 'normal', trend: '\u6B63\u5E38' },
          { name: '\u8840\u7EA2\u86CB\u767D', value: '145', unit: 'g/L', ref: '130-175', status: 'normal', trend: '\u6B63\u5E38' },
          { name: 'BMI', value: '24.5', unit: 'kg/m2', ref: '18.5-24.9', status: 'normal', trend: '\u6B63\u5E38' }
        ]
      },
      {
        id: 3, title: '\u4E2D\u533B\u4F53\u8D28\u8FA8\u8BC6', report_date: '2025-12-10',
        status: 'parsed', file_size: 262144, tags: ['\u4E2D\u533B'],
        indicators: [
          { name: '\u6C14\u865A\u8D28\u5F97\u5206', value: '68', unit: '\u5206', ref: '\u5F97\u5206>60\u4E3A\u503E\u5411', status: 'abnormal', trend: '\u503E\u5411' },
          { name: '\u5E73\u548C\u8D28\u5F97\u5206', value: '52', unit: '\u5206', ref: '\u5F97\u5206>60\u4E3A\u503E\u5411', status: 'normal', trend: '\u6B63\u5E38' }
        ]
      }
    ],
    foodRecipes: [
      {
        name: '\u9EC4\u82AA\u7EA2\u67A3\u8336', effect: '\u8865\u6C14\u5347\u9633\uFF0C\u56FA\u8868\u6B62\u6C57\uFF0C\u589E\u5F3A\u514D\u75AB\u529B',
        ingredients: ['\u9EC4\u82AA 15g', '\u7EA2\u67A3 5\u679A', '\u67B8\u6737 10g'],
        method: '\u9EC4\u82AA\u3001\u7EA2\u67A3\u6D17\u51C0\uFF0C\u52A0\u6C34800ml\uFF0C\u5927\u706B\u716E\u6CB8\u540E\u8F6C\u5C0F\u706B\u716E20\u5206\u949F\uFF0C\u52A0\u5165\u67B8\u6737\u518D\u716E5\u5206\u949F\u5373\u53EF\u3002',
        frequency: '\u6BCF\u65E51\u5242', duration: '\u716E25\u5206\u949F', featured: true, gradient: 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)', emoji: '&#129379;'
      },
      {
        name: '\u5C71\u836F\u5C0F\u7C73\u7CA5', effect: '\u5065\u813E\u76CA\u6C14\uFF0C\u517B\u80C3\u8865\u865A',
        ingredients: ['\u5C71\u836F 100g', '\u5C0F\u7C73 50g', '\u7EA2\u67A3 3\u679A'],
        method: '\u5C71\u836F\u53BB\u76AE\u5207\u5757\uFF0C\u4E0E\u5C0F\u7C73\u3001\u7EA2\u67A3\u540C\u716E\u81F3\u7CA5\u7A20\u3002',
        frequency: '\u65E9\u9910\u98DF\u7528', duration: '\u716E30\u5206\u949F', featured: false, gradient: 'linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)', emoji: '&#127859;'
      },
      {
        name: '\u515A\u53C2\u7096\u9E21\u6C64', effect: '\u8865\u4E2D\u76CA\u6C14\uFF0C\u517B\u8840\u751F\u6D25',
        ingredients: ['\u515A\u53C2 20g', '\u6BCD\u9E21 \u534A\u53EA', '\u7EA2\u67A3 5\u679A'],
        method: '\u9E21\u8089\u7130\u6C34\uFF0C\u4E0E\u515A\u53C2\u3001\u7EA2\u67A3\u540C\u70961.5\u5C0F\u65F6\uFF0C\u52A0\u76D0\u8C03\u5473\u3002',
        frequency: '\u6BCF\u54682\u6B21', duration: '\u709690\u5206\u949F', featured: false, gradient: 'linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%)', emoji: '&#129379;'
      },
      {
        name: '\u56DB\u795E\u6C64', effect: '\u5065\u813E\u795B\u6E7F\uFF0C\u76CA\u6C14\u8865\u865A',
        ingredients: ['\u832F\u82D3 15g', '\u5C71\u836F 15g', '\u83B2\u5B50 15g', '\u82A1\u5B9E 15g'],
        method: '\u56DB\u5473\u836F\u6750\u6D17\u51C0\uFF0C\u52A0\u6C34500ml\uFF0C\u716E\u81F3\u83B2\u5B50\u8F6F\u70C2\u5373\u53EF\u3002',
        frequency: '\u6BCF\u54683\u6B21', duration: '\u716E40\u5206\u949F', featured: false, gradient: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)', emoji: '&#127858;'
      }
    ],
    consultantReviews: [
      { id: 1, user_name: '\u674E\u5EFA\u56FD', user_avatar: '\u674E', gender: '\u7537', age: 58, date: '2026-07-20', analysis: '2\u578B\u7CD6\u5C3F\u75C5\u98CE\u9669 (ICD-11: 5A11)', confidence: 87 },
      { id: 2, user_name: '\u738B\u79C0\u82B3', user_avatar: '\u738B', gender: '\u5973', age: 45, date: '2026-07-20', analysis: '\u9AD8\u8102\u8840\u75C7\u98CE\u9669 (ICD-11: 5C70)', confidence: 92 },
      { id: 3, user_name: '\u9648\u4F1F', user_avatar: '\u9648', gender: '\u7537', age: 35, date: '2026-07-19', analysis: '\u9AD8\u8840\u538B\u98CE\u9669 (ICD-11: BA00)', confidence: 78 }
    ],
    consultantStats: { pending: 24, today_plans: 8, my_users: 156, accuracy: '92%' },
    reports: [
      { id: 'r1', name: '2026\u5E74\u5E74\u5EA6\u4F53\u68C0\u62A5\u544A', type: 'checkup', typeName: '\u4F53\u68C0\u62A5\u544A', date: '2026-06-15', size: '2.4 MB', status: 'parsed', icon: 'clipboard' },
      { id: 'r2', name: '\u5168\u57FA\u56E0\u7EC4\u68C0\u6D4B\u62A5\u544A', type: 'genetic', typeName: '\u57FA\u56E0\u68C0\u6D4B', date: '2026-05-20', size: '8.1 MB', status: 'parsed', icon: 'dna' },
      { id: 'r3', name: '\u80F8\u90E8CT\u589E\u5F3A\u626B\u63CF', type: 'imaging', typeName: '\u5F71\u50CF\u68C0\u67E5', date: '2026-04-10', size: '15.6 MB', status: 'parsed', icon: 'scan' },
      { id: 'r4', name: '\u8840\u5E38\u89C4+\u751F\u5316\u5168\u5957', type: 'lab', typeName: '\u68C0\u9A8C\u5355', date: '2026-06-15', size: '0.8 MB', status: 'parsed', icon: 'test_tube' },
      { id: 'r5', name: '\u7CD6\u5316\u8840\u7EA2\u86CB\u767D\u7F29\u5408\u7269\u68C0\u6D4B', type: 'lab', typeName: '\u68C0\u9A8C\u5355', date: '2026-03-22', size: '0.5 MB', status: 'parsed', icon: 'test_tube' },
      { id: 'r6', name: '\u4E2D\u533B\u8FA8\u8BC1\u95EE\u5377', type: 'tcm', typeName: '\u4E2D\u533B\u95EE\u8BCA', date: '2026-07-01', size: '0.2 MB', status: 'pending', icon: 'leaf' }
    ],
    repair: {
      score: 75,
      scoreTrend: +5,
      repairAge: 52,
      calendarAge: 54,
      percentile: 68,
      status: '良好',
      damageModes: [
        { name: '线粒体功能不足', level: 'primary' },
        { name: '轻度氧化应激', level: 'secondary' },
        { name: '慢性炎症倾向', level: 'secondary' }
      ],
      dailyPillars: [
        { name: '睡眠修复', icon: '🌙', score: 62, detail: '深睡不足，建议23:00前入睡', priority: 'high', evidence: 'A级' },
        { name: '营养优化', icon: '🥗', score: 72, detail: '抗氧化物摄入不足', priority: 'medium', evidence: 'B+级' },
        { name: '运动激活', icon: '🏃', score: 45, detail: '本周运动3次，需增加到5次', priority: 'high', evidence: 'A级' },
        { name: '频率干预', icon: '🎵', score: 65, detail: '五音疗法·宫调健脾', priority: 'medium', evidence: 'B级' }
      ],
      plan: [
        { time: '22:00', title: '🌙 睡前准备', desc: '温水浴 15min → 核心体温下降 0.5°C → 促进入睡', tag: 'sleep', tagLabel: '睡眠' },
        { time: '22:30', title: '🎵 五音助眠', desc: '播放宫调音频 30min → 健脾安神 → 诱导深睡', tag: 'frequency', tagLabel: '五音' },
        { time: '07:00', title: '🥗 营养早餐', desc: '山药红枣粥 + 黄芪枸杞茶 → 补充修复原料 → 增强线粒体功能', tag: 'nutrition', tagLabel: '营养' },
        { time: '16:00', title: '🏃 抗阻训练', desc: 'HIIT 20min → 激活 AMPK 通路 → 当晚 GH 脉冲增强', tag: 'exercise', tagLabel: '运动' },
        { time: '全天', title: '🌿 药食同源调理', desc: '黄芪枸杞茶 每日1剂 → 多靶点细胞修复', tag: 'food_med', tagLabel: '药食' }
      ],
      trend: {
        dates: ['07-09', '07-10', '07-11', '07-12', '07-13', '07-14', '07-15'],
        scores: [62, 64, 63, 66, 68, 70, 75],
        deepSleep: [42, 45, 40, 48, 50, 49, 52],
        hrv: [42, 43, 41, 44, 45, 46, 48]
      },
      foodMedicine: [
        {
          name: '黄芪枸杞茶',
          form: '代茶饮',
          ingredients: ['黄芪 6g', '枸杞 6g', '红枣 3枚'],
          repair_target: '线粒体能量代谢',
          pathway: 'AMPK通路激活 → PGC-1α → 线粒体生物发生',
          usage: '沸水冲泡，代茶频饮，每日1剂',
          evidence: 'B+级',
          source: '《本草纲目》药食两用方',
          color: '#0d8a6a'
        },
        {
          name: '山药薏米粥',
          form: '养生粥',
          ingredients: ['怀山药 30g', '炒薏米 30g', '粳米 50g'],
          repair_target: '代谢细胞修复',
          pathway: 'AMPK激活 → 改善胰岛素敏感性 → 糖脂代谢平衡',
          usage: '每日早餐食用，连续14天',
          evidence: 'B级',
          source: '《神农本草经》上品药食',
          color: '#d97706'
        },
        {
          name: '麦冬玉竹汤',
          form: '药膳汤',
          ingredients: ['麦冬 10g', '玉竹 10g', '瘦肉 150g'],
          repair_target: '抗氧化防御',
          pathway: 'Nrf2/ARE通路激活 → SOD/CAT/GPx上调 → ROS清除',
          usage: '每周2-3次，煲汤饮用',
          evidence: 'B级',
          source: '《温病条辨》养阴方',
          color: '#0284c7'
        },
        {
          name: '丹参山楂饮',
          form: '代茶饮',
          ingredients: ['丹参 3g', '山楂 6g', '冰糖 适量'],
          repair_target: '血管内皮修复',
          pathway: 'eNOS激活 → NO合成增加 → 内皮功能改善',
          usage: '沸水冲泡，代茶饮用',
          evidence: 'A级',
          source: '《本草纲目》活血方',
          color: '#dc2626'
        },
        {
          name: '茯苓陈皮茶',
          form: '代茶饮',
          ingredients: ['茯苓 10g', '陈皮 3g', '甘草 2g'],
          repair_target: '代谢细胞修复',
          pathway: 'AMPK磷酸化 → 胰岛素敏感性改善 → 脂质代谢调节',
          usage: '每日1剂，沸水冲泡',
          evidence: 'B级',
          source: '《太平惠民和剂局方》二陈汤化裁',
          color: '#7c3aed'
        },
        {
          name: '百合莲子粥',
          form: '养生粥',
          ingredients: ['百合 15g', '莲子 15g', '糯米 50g', '冰糖 适量'],
          repair_target: '自主神经调节',
          pathway: 'GABA能系统调节 → 副交感活性增强 → HRV改善',
          usage: '晚餐食用，宁心安神',
          evidence: 'B级',
          source: '《金匮要略》百合方',
          color: '#16a34a'
        }
      ]
    },
    sleep: {
      score: 62,
      scoreLabel: '\u9700\u6539\u5584',
      deepSleep: 52,
      deepSleepUnit: 'min',
      deepSleepTarget: 90,
      bedtime: '23:30',
      sleepEfficiency: 85,
      awakenings: 3,
      totalDuration: '7h12min',
      metrics: [
        { label: '\u6DF1\u7761\u65F6\u957F', value: '52', unit: 'min', target: '90min', status: 'warning' },
        { label: '\u5165\u7761\u65F6\u95F4', value: '23:30', unit: '', target: '23:00\u524D', status: 'warning' },
        { label: '\u5165\u7761\u6548\u7387', value: '85%', unit: '', target: '>90%', status: 'normal' },
        { label: '\u89C9\u9192\u6B21\u6570', value: '3', unit: '\u6B21', target: '<2\u6B21', status: 'warning' }
      ],
      weights: [
        { label: '\u6DF1\u5EA6\u7761\u7720', weight: '25%', value: 62 },
        { label: 'HRV\u6062\u590D', weight: '20%', value: 70 },
        { label: '\u708E\u75C7\u6C34\u5E73', weight: '15%', value: 58 },
        { label: '\u8FD0\u52A8\u4F9D\u4ECE', weight: '15%', value: 45 },
        { label: '\u8425\u517B\u8D28\u91CF', weight: '10%', value: 72 },
        { label: '\u663C\u591C\u8282\u5F8B', weight: '10%', value: 80 },
        { label: '\u4E3B\u89C2\u7CBE\u529B', weight: '5%', value: 75 }
      ],
      trend: {
        scores: [58, 60, 55, 62, 65, 60, 62],
        dates: ['07-15', '07-16', '07-17', '07-18', '07-19', '07-20', '07-21']
      },
      tones: [
        { name: '\u5BAB\u8C03', effect: '\u5065\u813E\u5B89\u795E', color: '#0d8a6a', active: false },
        { name: '\u5546\u8C03', effect: '\u6DA6\u80BA\u5B81\u5FC3', color: '#0077b6', active: false },
        { name: '\u89D2\u8C03', effect: '\u758F\u809D\u89E3\u90C1', color: '#16a34a', active: false },
        { name: '\u5FBD\u8C03', effect: '\u517B\u5FC3\u5B89\u795E', color: '#dc2626', active: false },
        { name: '\u7FBD\u8C03', effect: '\u8865\u80BE\u76CA\u7CBE', color: '#7c3aed', active: false }
      ],
      checklist: [
        { id: 'sl1', text: '\u6E29\u6C34\u6D74 15min', checked: true },
        { id: 'sl2', text: '\u5173\u95ED\u84DD\u5149\u8BBE\u5907', checked: true },
        { id: 'sl3', text: '\u5367\u5BA4\u6E29\u5EA6 20-22\u00B0C', checked: false },
        { id: 'sl4', text: '\u9178\u67A3\u4EC1\u5B89\u795E\u65B9 150ml', checked: false }
      ]
    },
    tcm: {
      constitution: {
        type: '气虚质',
        score: 72,
        radar: [72, 45, 38, 55, 30, 28, 42, 35, 20, 68, 25, 50],
        labels: ['平和质', '气虚质', '阳虚质', '阴虚质', '痰湿质', '湿热质', '血瘀质', '气郁质', '特禀质'],
        advice: {
          diet: '多食补气食物：黄芪炖鸡、山药粥、大枣',
          lifestyle: '避免过度劳累，午休20-30分钟',
          exercise: '八段锦、太极拳，每日30分钟',
          emotion: '保持心情舒畅，避免思虑过度'
        }
      },
      herbs: [
        {
          name: '黄芪',
          category: '补气药',
          repair_pathway: 'AMPK通路激活 → 线粒体生物发生 → ATP合成增加',
          target: '线粒体功能',
          mechanism: '增强AMPK活性，促进PGC-1α表达，提升线粒体自噬和再生',
          evidence: 'A级',
          color: '#0d8a6a'
        },
        {
          name: '人参',
          category: '补气药',
          repair_pathway: 'SIRT1激活 → NAD+代谢 → 细胞能量稳态',
          target: '细胞能量代谢',
          mechanism: '人参皂苷Rg1激活SIRT1通路，促进NAD+合成，改善线粒体功能',
          evidence: 'A级',
          color: '#0d8a6a'
        },
        {
          name: '丹参',
          category: '活血化瘀药',
          repair_pathway: 'eNOS激活 → NO合成增加 → 血管内皮修复',
          target: '血管内皮修复',
          mechanism: '丹参酮IIA促进内皮型一氧化氮合酶(eNOS)活性，改善微循环',
          evidence: 'A级',
          color: '#dc2626'
        },
        {
          name: '麦冬',
          category: '滋阴药',
          repair_pathway: 'Nrf2激活 → 抗氧化酶表达 → ROS清除',
          target: '抗氧化防御',
          mechanism: '麦冬皂苷激活Nrf2/ARE通路，上调SOD、CAT、GPx等抗氧化酶',
          evidence: 'B+级',
          color: '#0284c7'
        },
        {
          name: '枸杞',
          category: '滋阴药',
          repair_pathway: '端粒酶激活 → 端粒保护 → 细胞衰老延缓',
          target: '端粒保护',
          mechanism: '枸杞多糖激活端粒酶(TERT)表达，保护染色体末端免受缩短',
          evidence: 'B级',
          color: '#7c3aed'
        },
        {
          name: '茯苓',
          category: '利水渗湿药',
          repair_pathway: 'AMPK激活 → 胰岛素敏感性改善 → 代谢修复',
          target: '代谢细胞修复',
          mechanism: '茯苓多糖增强AMPK磷酸化，改善胰岛素抵抗和脂质代谢',
          evidence: 'B级',
          color: '#d97706'
        }
      ],
      formulas: [
        {
          name: '四君子汤',
          source: '《太平惠民和剂局方》',
          composition: ['人参 9g', '白术 9g', '茯苓 9g', '甘草 6g'],
          repair_targets: ['线粒体功能', '细胞能量代谢', '代谢细胞修复'],
          evidence: 'A级',
          description: '补气健脾的经典方，四味药协同增强AMPK-SIRT1-PGC-1α轴，系统性提升细胞能量代谢'
        },
        {
          name: '生脉散',
          source: '《医学启源》',
          composition: ['人参 10g', '麦冬 15g', '五味子 6g'],
          repair_targets: ['线粒体功能', '抗氧化防御', '心血管内皮修复'],
          evidence: 'A级',
          description: '益气养阴复脉，人参+麦冬协同激活AMPK和Nrf2双通路，同时提升能量和抗氧化'
        }
      ]
    },
    growth: {
      streak: 5,
      totalDays: 23,
      level: 3,
      levelName: '健康达人',
      points: 1280,
      nextLevelPoints: 2000,
      weeklyReport: {
        weekStart: '07-14',
        weekEnd: '07-20',
        checkins: 5,
        sleepAvg: 64,
        exerciseCount: 3,
        nutritionScore: 72,
        improvement: '+3.2',
        topAction: '坚持早睡（23:00前入睡5天）',
        suggestions: ['深睡时长仍不足，建议睡前1小时停用电子设备', '本周运动3次，保持良好！', '可以尝试增加午休时间以提升日间精力']
      },
      achievements: [
        { id: 'a1', name: '初试锋芒', desc: '首次完成健康打卡', icon: 'star', unlocked: true, date: '07-01' },
        { id: 'a2', name: '七日如一', desc: '连续7天打卡', icon: 'fire', unlocked: true, date: '07-07' },
        { id: 'a3', name: '早睡早起', desc: '连续3天23:00前入睡', icon: 'moon', unlocked: true, date: '07-10' },
        { id: 'a4', name: '运动达人', desc: '单周运动5次', icon: 'running', unlocked: false },
        { id: 'a5', name: '修复先锋', desc: '修复评分突破80分', icon: 'heart', unlocked: false },
      ],
      dailyCheckin: {
        '07-21': { sleep: true, exercise: false, nutrition: true, checklist: false, tcm: false },
        '07-20': { sleep: true, exercise: true, nutrition: true, checklist: true, tcm: true },
        '07-19': { sleep: true, exercise: true, nutrition: false, checklist: false, tcm: false },
        '07-18': { sleep: false, exercise: true, nutrition: true, checklist: true, tcm: false },
        '07-17': { sleep: true, exercise: false, nutrition: true, checklist: false, tcm: true },
      }
    },
    gene_risks: [
      { gene: 'MTHFR C677T', function: '叶酸代谢 / 同型半胱氨酸', risk: 'high', riskLabel: '高风险', action: '补充活性叶酸(5-MTHF)' },
      { gene: 'APOE ε4', function: '脂质代谢 / 阿尔茨海默风险', risk: 'moderate', riskLabel: '中风险', action: '控制饱和脂肪，增加Omega-3' },
      { gene: 'ACE I/D', function: '血管紧张素 / 血压调节', risk: 'moderate', riskLabel: '中风险', action: '限盐、有氧运动、监测血压' },
      { gene: 'BDNF Val66Met', function: '脑源性神经营养因子', risk: 'low', riskLabel: '低风险', action: '规律运动促进BDNF分泌' },
      { gene: 'CLOCK 3111T>C', function: '昼夜节律调控', risk: 'high', riskLabel: '高风险', action: '严格固定作息、晨间光照' },
      { gene: 'SIRT3 rs7895833', function: '线粒体去乙酰化', risk: 'low', riskLabel: '低风险', action: 'NAD+前体补充、间歇性禁食' }
    ],
    damage_patterns: [
      { pattern: '线粒体功能不足', severity: 'high', severityLabel: '重度', desc: 'ATP合成效率下降约35%，细胞能量供给不足，与气虚质高度吻合', markers: ['ATP↓35%', 'AMPK活性↓', 'PGC-1α↓'], tcm: '中医对应：气虚 → 脾气虚 → 运化无力' },
      { pattern: '自主神经调节障碍', severity: 'moderate', severityLabel: '中度', desc: '交感/副交感平衡偏移，HRV低于同龄人第25百分位', markers: ['HRV↓25%', '夜间交感活跃', '皮质醇节律偏移'], tcm: '中医对应：心气虚 → 神明失养 → 悸动不安' },
      { pattern: '慢性低度炎症', severity: 'moderate', severityLabel: '中度', desc: 'CRP、IL-6轻度升高，处于代谢性炎症状态，与痰湿质倾向相关', markers: ['hs-CRP 2.1mg/L', 'IL-6↑', 'TNF-α↑'], tcm: '中医对应：痰湿内蕴 → 郁而化热 → 气机不畅' }
    ],
    tcm_cell_bridges: [
      { tcm: '气虚质', arrow: '→ AMPK通路 →', pathway: '线粒体生物发生受损，ATP合成效率下降', evidence: '黄芪激活AMPK（A级证据）' },
      { tcm: '心气虚', arrow: '→ HRV/内皮修复 →', pathway: '心脏自主神经调节减弱，血管内皮修复能力下降', evidence: '生脉散改善HRV（A级证据）' },
      { tcm: '痰湿质倾向', arrow: '→ mTOR/NF-κB →', pathway: '代谢炎症通路激活，慢性低度炎症状态', evidence: '茯苓调节mTOR（B级证据）' },
      { tcm: '阳虚质倾向', arrow: '→ Nrf2/SIRT →', pathway: '抗氧化防御和细胞修复能力整体下降', evidence: '麦冬激活Nrf2（B+级证据）' }
    ]
  };

  DEMO.today = {
    score: 75,
    scoreLabel: '良好',
    repairAge: 52.3,
    calendarAge: 54,
    ageDelta: -1.7,
    aiInsight: '您的深睡时长连续3天低于目标值，建议今晚尝试宫调健脾音乐辅助入睡。黄芪枸杞茶已连续饮用5天，线粒体能量指标正在改善中。',
    timeline: [
      { time: '07:00', items: ['温水浴15min', '黄芪枸杞茶冲泡'], tags: ['sleep', 'food_med'] },
      { time: '07:30', items: ['山药薏米粥早餐'], tags: ['nutrition'] },
      { time: '08:30', items: ['八段锦20min'], tags: ['exercise'] },
      { time: '12:00', items: ['麦冬玉竹汤午餐'], tags: ['food_med', 'nutrition'] },
      { time: '15:00', items: ['丹参山楂茶'], tags: ['food_med'] },
      { time: '17:00', items: ['散步30min'], tags: ['exercise'] },
      { time: '19:00', items: ['茯苓陈皮茶', '百合莲子粥'], tags: ['food_med', 'nutrition'] },
      { time: '21:30', items: ['关闭电子设备', '温水浴', '宫调五音15min'], tags: ['sleep', 'frequency'] },
      { time: '22:30', items: ['酸枣仁安神方', '入睡'], tags: ['sleep', 'food_med'] }
    ],
    metrics: [
      { label: '修复评分', value: '75', unit: '/100', trend: '+2', color: '#10b981' },
      { label: '深睡时长', value: '52', unit: 'min', trend: '-5', color: '#fbbf24' },
      { label: 'HRV恢复', value: '70', unit: 'ms', trend: '+3', color: '#10b981' },
      { label: '运动消耗', value: '320', unit: 'kcal', trend: '+45', color: '#0ea5e9' },
      { label: '营养评分', value: '72', unit: '/100', trend: '+1', color: '#10b981' },
      { label: '入睡效率', value: '85', unit: '%', trend: '+2', color: '#10b981' }
    ]
  };

  DEMO.trends = {
    scores7: [70, 72, 68, 73, 75, 73, 75],
    scores30: [62, 65, 63, 67, 68, 70, 69, 72, 71, 73, 72, 74, 71, 73, 75, 74, 76, 73, 75, 74, 72, 75, 73, 76, 74, 75, 73, 72, 75],
    scores90: [55, 58, 56, 60, 59, 61, 60, 63, 62, 64, 63, 65, 64, 66, 65, 67, 66, 68, 67, 69, 68, 70, 69, 71, 70, 72, 71, 73, 72, 74, 73, 75, 74, 73, 75, 74, 72, 73, 75, 74, 73, 75, 74, 73, 72, 74, 73, 75, 74, 72, 74, 73, 75, 74, 72, 73, 75, 74, 73, 75, 74, 73, 72, 75, 74, 73, 75, 74, 72, 73, 75, 74, 73, 75, 74, 72, 74, 73, 75, 74, 72, 73, 75, 74, 73, 75],
    ages7: [53.1, 52.8, 53.2, 52.7, 52.5, 52.6, 52.3],
    ages30: [54.5, 54.2, 53.9, 53.7, 53.5, 53.3, 53.1, 52.9, 52.8, 52.7, 52.6, 52.5, 52.4, 52.3, 52.2, 52.1, 52.0, 51.9, 51.8, 51.7, 51.6, 51.5, 51.4, 51.3, 51.2, 51.1, 51.0, 50.9, 50.8],
    ages90: [56.2, 56.0, 55.8, 55.6, 55.4, 55.2, 55.0, 54.8, 54.6, 54.4, 54.2, 54.0, 53.8, 53.6, 53.4, 53.2, 53.0, 52.8, 52.6, 52.4, 52.2, 52.0, 51.8, 51.6, 51.4, 51.2, 51.0, 50.8, 50.6, 50.4],
    dates7: ['07-15', '07-16', '07-17', '07-18', '07-19', '07-20', '07-21'],
    dates30: ['06-22', '06-23', '06-24', '06-25', '06-26', '06-27', '06-28', '06-29', '06-30', '07-01', '07-02', '07-03', '07-04', '07-05', '07-06', '07-07', '07-08', '07-09', '07-10', '07-11', '07-12', '07-13', '07-14', '07-15', '07-16', '07-17', '07-18', '07-19', '07-20', '07-21'],
    dates90: Array.from({length: 90}, function(_, i) { var d = new Date(2026, 3, 23 + i); return (d.getMonth()+1).toString().padStart(2,'0') + '-' + d.getDate().toString().padStart(2,'0'); }),
    dimensions: [
      { name: '深度睡眠', score: 62, trend: '+3', color: '#10b981' },
      { name: 'HRV恢复', score: 70, trend: '+5', color: '#0ea5e9' },
      { name: '炎症水平', score: 58, trend: '-2', color: '#f87171' },
      { name: '运动依从', score: 45, trend: '+8', color: '#fbbf24' },
      { name: '营养质量', score: 72, trend: '+1', color: '#10b981' },
      { name: '昼夜节律', score: 80, trend: '+3', color: '#10b981' },
      { name: '主观精力', score: 75, trend: '+2', color: '#10b981' }
    ]
  };

  // ==================== DOM Elements ====================
  var landingView = document.getElementById('landing-view');
  var authModal = document.getElementById('auth-modal');
  var appView = document.getElementById('app-view');
  var loginForm = document.getElementById('login-form');
  var registerForm = document.getElementById('register-form');
  var phoneForm = document.getElementById('phone-form');
  var authTabs = document.querySelectorAll('.auth-tab');
  var navItems = document.querySelectorAll('.nav-item');
  var pages = document.querySelectorAll('.page');
  var logoutBtn = document.getElementById('logout-btn');
  var uploadModal = document.getElementById('upload-modal');
  var uploadBtn = document.getElementById('upload-report-btn');
  var modalClose = document.querySelectorAll('.modal-close');
  var modalOverlay = document.querySelectorAll('.modal-overlay');
  var trendTabs = document.querySelectorAll('.trend-tab');
  var dropzone = document.getElementById('upload-dropzone');
  var fileInput = document.getElementById('file-input');

  // ==================== Loading / Skeleton Helpers ====================
  function showSpinner(container) {
    if (!container) return;
    container.innerHTML =
      '<div class="loading-spinner">' +
      '<div class="spinner-ring"></div>' +
      '<span>\u52A0\u8F7D\u4E2D...</span>' +
      '</div>';
  }

  function showSkeleton(container, lines) {
    if (!container) return;
    lines = lines || 3;
    var html = '';
    for (var i = 0; i < lines; i++) {
      var w = i === lines - 1 ? ' w60' : '';
      html += '<div class="skeleton skeleton-line' + w + '"></div>';
    }
    container.innerHTML = html;
  }

  function showSkeletonCards(container, count) {
    if (!container) return;
    count = count || 3;
    var html = '';
    for (var i = 0; i < count; i++) {
      html += '<div class="skeleton skeleton-card"></div>';
    }
    container.innerHTML = html;
  }

  function formatFileSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    // Convert ISO date to MM-DD for chart display
    if (dateStr.length >= 10) {
      return dateStr.substring(5, 10);
    }
    return dateStr;
  }

  function getScoreBadgeClass(score) {
    if (score >= 80) return '\u826F\u597D';
    if (score >= 60) return '\u4E00\u822C';
    return '\u8F83\u5DEE';
  }

  function getScoreBadgeType(score) {
    if (score >= 80) return 'success';
    if (score >= 60) return 'warning';
    return 'error';
  }

  // ==================== Auth ====================
  authTabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      authTabs.forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var target = tab.dataset.tab;
      if (target === 'login') {
        loginForm.classList.add('active');
        registerForm.classList.remove('active');
      } else {
        loginForm.classList.remove('active');
        registerForm.classList.add('active');
      }
    });
  });

  loginForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var emailInput = loginForm.querySelector('input[type="email"]');
    var passwordInput = loginForm.querySelector('input[type="password"]');
    var email = emailInput.value.trim();
    var password = passwordInput.value;
    if (!email || !password) return;

    var submitBtn = loginForm.querySelector('button[type="submit"]');
    submitBtn.classList.add('loading');

    var data = await api('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: email, password: password })
    });

    submitBtn.classList.remove('loading');

    if (data) {
      saveTokens(data.access_token, data.refresh_token, data.user);
      hideDemoBanner();
      showSuccessToast('\u767B\u5F55\u6210\u529F');
      showAppView();
    } else if (!state.demoMode) {
      // API call returned null without entering demo mode, might be bad credentials
      showErrorToast('\u767B\u5F55\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u90AE\u7BB1\u548C\u5BC6\u7801');
    } else {
      // Demo mode fallback
      state.currentUser = DEMO.user;
      saveTokens('demo_access', 'demo_refresh', DEMO.user);
      showAppView();
    }
  });

  registerForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var nameInput = registerForm.querySelector('input[type="text"]');
    var emailInput = registerForm.querySelector('input[type="email"]');
    var phoneInput = registerForm.querySelector('input[type="tel"]');
    var passwordInput = registerForm.querySelector('input[type="password"]');
    var name = nameInput.value.trim();
    var email = emailInput.value.trim();
    var phone = phoneInput.value.trim();
    var password = passwordInput.value;
    if (!email || !password) return;

    var submitBtn = registerForm.querySelector('button[type="submit"]');
    submitBtn.classList.add('loading');

    var data = await api('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name: name, email: email, phone: phone, password: password })
    });

    submitBtn.classList.remove('loading');

    if (data) {
      saveTokens(data.access_token, data.refresh_token, data.user);
      hideDemoBanner();
      showSuccessToast('\u6CE8\u518C\u6210\u529F');
      showAppView();
    } else if (state.demoMode) {
      state.currentUser = DEMO.user;
      saveTokens('demo_access', 'demo_refresh', DEMO.user);
      showAppView();
    }
  });

  logoutBtn.addEventListener('click', function () {
    clearTokens();
    state.cache = {};
    state.constitutionType = null;
    state.constitutionScores = null;
    state.currentUser = null;
    landingView.classList.remove('hidden');
    appView.classList.add('hidden');
    authModal.classList.add('hidden');
    window.scrollTo(0, 0);
  });

  // 手机验证码：获取验证码（带 60s 倒计时）
  var sendCodeBtn = document.getElementById('send-code-btn');
  if (sendCodeBtn && phoneForm) {
    sendCodeBtn.addEventListener('click', async function () {
      var phoneInput = phoneForm.querySelector('input[name="phone"]');
      var phone = phoneInput.value.trim();
      if (!/^1[3-9]\d{9}$/.test(phone)) {
        showErrorToast('请输入有效的手机号');
        return;
      }
      sendCodeBtn.disabled = true;
      var sendData = await api('/api/v1/auth/send-sms-code', {
        method: 'POST',
        body: JSON.stringify({ phone: phone, purpose: 'login' })
      });
      if (sendData) {
        if (sendData.dev_code) {
          showSuccessToast('验证码已发送（开发模式：' + sendData.dev_code + '）');
        } else {
          showSuccessToast('验证码已发送，请查收短信');
        }
        var left = 60;
        sendCodeBtn.textContent = left + 's 后重发';
        var timer = setInterval(function () {
          left -= 1;
          if (left <= 0) {
            clearInterval(timer);
            sendCodeBtn.textContent = '获取验证码';
            sendCodeBtn.disabled = false;
          } else {
            sendCodeBtn.textContent = left + 's 后重发';
          }
        }, 1000);
      } else {
        sendCodeBtn.disabled = false;
      }
    });
  }

  // 手机验证码：登录 / 注册（账号不存在则自动注册）
  if (phoneForm) {
    phoneForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      var phoneInput = phoneForm.querySelector('input[name="phone"]');
      var codeInput = phoneForm.querySelector('input[name="code"]');
      var phone = phoneInput.value.trim();
      var code = codeInput.value.trim();
      if (!/^1[3-9]\d{9}$/.test(phone) || !code) return;

      var submitBtn = phoneForm.querySelector('button[type="submit"]');
      submitBtn.classList.add('loading');

      var data = await api('/api/v1/auth/phone-login', {
        method: 'POST',
        body: JSON.stringify({ phone: phone, code: code })
      });

      submitBtn.classList.remove('loading');

      if (data) {
        saveTokens(data.access_token, data.refresh_token, data.user);
        hideDemoBanner();
        showSuccessToast('登录成功');
        showAppView();
      } else if (!state.demoMode) {
        showErrorToast('验证码错误，请重新获取');
      }
    });
  }

  async function loadCurrentUser() {
    var data = await api('/api/v1/auth/me', { silent: true });
    if (data) {
      state.currentUser = data;
      localStorage.setItem('healthlens_user', JSON.stringify(data));
      hideDemoBanner();
      return data;
    }
    // Fallback to stored user
    var stored = getStoredUser();
    if (stored) {
      state.currentUser = stored;
      return stored;
    }
    return null;
  }

  function updateSidebarUser() {
    var user = state.currentUser;
    if (!user) return;
    var nameEl = document.querySelector('.user-name');
    var roleEl = document.querySelector('.user-role');
    var avatarEl = document.querySelector('.user-avatar');
    if (nameEl) nameEl.textContent = user.name || user.username || '\u7528\u6237';
    if (roleEl) roleEl.textContent = user.role === 'consultant' ? '\u987E\u95EE' : '\u7528\u6237';
    if (avatarEl) avatarEl.textContent = (user.name || user.username || '\u7528\u6237').charAt(0);

    // Show/hide consultant nav item based on role
    var consultantNav = document.querySelector('.nav-item[data-page="consultant"]');
    if (consultantNav) {
      consultantNav.style.display = (user.role === 'consultant') ? '' : 'none';
    }
  }

  // ==================== View Management ====================
  function showAppropriateView() {
    if (isLoggedIn()) {
      showAppView();
    } else {
      landingView.classList.remove('hidden');
      appView.classList.add('hidden');
      authModal.classList.add('hidden');
    }
  }

  function showAppView() {
    landingView.classList.add('hidden');
    authModal.classList.add('hidden');
    appView.classList.remove('hidden');
    updateSidebarUser();
    // 加载积分余额到顶栏
    loadPointsBalance();
    // 初始化：隐藏所有旧页面，激活今日页
    switchPage('today');
    setTimeout(function () {
      loadPageData('today');
    }, 100);
  }

  // Open auth modal (login / register / phone tab)
  function openAuthModal(tab) {
    authModal.classList.remove('hidden');
    authTabs.forEach(function (t) { t.classList.remove('active'); });
    var targetTab = authModal.querySelector('.auth-tab[data-tab="' + tab + '"]');
    if (targetTab) targetTab.classList.add('active');
    // 隐藏所有表单，再显示目标表单（表单 id 约定为 {tab}-form）
    [loginForm, registerForm, phoneForm].forEach(function (f) {
      if (f) f.classList.remove('active');
    });
    var targetForm = document.getElementById(tab + '-form');
    if (targetForm) targetForm.classList.add('active');
  }

  // ==================== Auth Modal Triggers ====================
  // Nav bar buttons
  var navLoginBtn = document.getElementById('nav-login-btn');
  var navRegisterBtn = document.getElementById('nav-register-btn');
  if (navLoginBtn) navLoginBtn.addEventListener('click', function () { openAuthModal('login'); });
  if (navRegisterBtn) navRegisterBtn.addEventListener('click', function () { openAuthModal('register'); });

  // Hero buttons
  var heroStartBtn = document.getElementById('hero-start-btn');
  var heroLearnBtn = document.getElementById('hero-learn-btn');
  if (heroStartBtn) heroStartBtn.addEventListener('click', function () { openAuthModal('register'); });
  if (heroLearnBtn) heroLearnBtn.addEventListener('click', function () {
    var featuresEl = document.getElementById('features');
    if (featuresEl) featuresEl.scrollIntoView({ behavior: 'smooth' });
  });

  // CTA buttons
  var ctaRegisterBtn = document.getElementById('cta-register-btn');
  var ctaDemoBtn = document.getElementById('cta-demo-btn');
  if (ctaRegisterBtn) ctaRegisterBtn.addEventListener('click', function () { openAuthModal('register'); });
  if (ctaDemoBtn) ctaDemoBtn.addEventListener('click', function () {
    state.currentUser = DEMO.user;
    saveTokens('demo_access', 'demo_refresh', DEMO.user);
    showAppView();
  });

  // Modal close (all modals)
  modalClose.forEach(function (btn) {
    btn.addEventListener('click', function () {
      this.closest('.modal').classList.add('hidden');
    });
  });
  modalOverlay.forEach(function (overlay) {
    overlay.addEventListener('click', function () {
      this.closest('.modal').classList.add('hidden');
    });
  });

  // ==================== Navigation ====================
  navItems.forEach(function (item) {
    item.addEventListener('click', function (e) {
      e.preventDefault();
      var page = item.dataset.page;
      if (!page) return;
      switchPage(page);
      navItems.forEach(function (n) { n.classList.remove('active'); });
      item.classList.add('active');
    });
  });

  document.querySelectorAll('.link-sm[data-page]').forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      var page = link.dataset.page;
      switchPage(page);
      navItems.forEach(function (n) {
        n.classList.toggle('active', n.dataset.page === page);
      });
    });
  });

  // 底部Tab导航点击
  document.querySelectorAll('.tab-item').forEach(function(tab) {
    tab.addEventListener('click', function(e) {
      e.preventDefault();
      var page = this.dataset.page;
      document.querySelectorAll('.tab-item').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      switchPage(page);
    });
  });

  // 方案页健康知识入口
  document.querySelectorAll('.knowledge-entry').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.preventDefault();
      switchPage('knowledge');
    });
  });

  function switchPage(page) {
    document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); p.style.display = 'none'; });
    var target = document.getElementById('page-' + page);
    if (target) {
      target.classList.add('active');
      target.style.display = 'block';
      var titleEl = document.querySelector('.page-title');
      if (titleEl) titleEl.textContent = getPageTitle(page);
      state.currentPage = page;
      // 同步底部Tab active 状态
      document.querySelectorAll('.tab-item').forEach(function(t) {
        t.classList.toggle('active', t.dataset.page === page);
      });
      loadPageData(page);
    }
  }

  function getPageTitle(page) {
    var titles = {
      dashboard: '\u5065\u5EB7\u5168\u666F',
      analysis: '\u5065\u5EB7\u5206\u6790',
      plan: '\u4FEE\u590D\u65B9\u6848',
      reports: '\u62A5\u544A\u4E2D\u5FC3',
      growth: '\u6210\u957F\u4E2D\u5FC3',
      consultant: '\u5065\u5EB7\u65B9\u6848\u5DE5\u4F5C\u53F0',
      today: '今日',
      trends: '趋势',
      profile: '我的',
      // 兼容旧页面
      records: '\u5065\u5EB7\u5168\u666F',
      tcm: '\u4FEE\u590D\u8BCA\u65AD',
      food: '\u4FEE\u590D\u65B9\u6848',
      nonpharma: '\u4FEE\u590D\u65B9\u6848',
      risk: '\u4FEE\u590D\u8BCA\u65AD',
      repair: '\u5065\u5EB7\u5168\u666F',
      sleep: '\u4FEE\u590D\u65B9\u6848'
    };
    return titles[page] || 'HealthLens';
  }

  // ==================== Analytics & Feedback & Growth APIs ====================
  async function trackEvent(eventType, page, element, metadata) {
    if (state.demoMode) return;
    try {
      await api('/api/v1/analytics/event', {
        method: 'POST',
        body: JSON.stringify({
          event_type: eventType,
          page: page || state.currentPage,
          element: element || null,
          timestamp: new Date().toISOString(),
          metadata: metadata || {}
        }),
        silent: true
      });
    } catch (e) { /* silent fail */ }
  }

  async function trackSession() {
    if (state.demoMode) return;
    try {
      await api('/api/v1/analytics/session', {
        method: 'POST',
        body: JSON.stringify({
          session_id: 'sess_' + Date.now(),
          duration_seconds: Math.floor(Math.random() * 300) + 60,
          pages_visited: [state.currentPage],
          actions_count: 1
        }),
        silent: true
      });
    } catch (e) { /* silent fail */ }
  }

  async function submitFeedback(resultId, rating, text) {
    if (state.demoMode) {
      showSuccessToast('感谢你的评价！（演示模式）');
      return true;
    }
    var result = await api('/api/v1/feedback/satisfaction', {
      method: 'POST',
      body: JSON.stringify({
        result_id: resultId || 'demo-result',
        rating: rating,
        feedback_text: text || null,
        tags: []
      })
    });
    if (result) {
      showSuccessToast('感谢你的评价！');
    }
    return !!result;
  }

  async function submitEffect(resultId, metricType, before, after, days) {
    if (state.demoMode) {
      showSuccessToast('效果追踪已记录（演示模式）');
      return true;
    }
    var result = await api('/api/v1/feedback/effect', {
      method: 'POST',
      body: JSON.stringify({
        result_id: resultId || 'demo-result',
        metric_type: metricType,
        before_value: before,
        after_value: after,
        days_elapsed: days
      })
    });
    if (result) {
      showSuccessToast('效果追踪已记录');
    }
    return !!result;
  }

  async function generateShareLink(contentType, contentId) {
    // 信任护栏：演示/不可用结果（非用户真实分析）禁止分享
    if (state.resultReadOnly && contentType !== 'app') {
      showErrorToast('演示/不可用结果不可分享，请使用你的真实分析结果');
      return { share_url: '', share_text: '' };
    }
    if (state.demoMode) {
      var base = 'https://healthlens.cc';
      var url = contentType === 'plan' ? base + '/plan/' + (contentId || 'default') :
                contentType === 'knowledge' ? base + '/knowledge/' + (contentId || 'intro') :
                base;
      return { share_url: url, share_text: '推荐 HealthLens —— AI 驱动的健康全景平台' };
    }
    var result = await api('/api/v1/growth/share', {
      method: 'POST',
      body: JSON.stringify({ content_type: contentType, content_id: contentId || null })
    });
    return result || { share_url: 'https://healthlens.cc', share_text: '推荐 HealthLens' };
  }

  async function generateInviteCode() {
    if (state.demoMode) {
      return { invite_code: 'HL' + Math.random().toString(36).substring(2, 8).toUpperCase(), invite_url: 'https://healthlens.cc/register?invite=DEMO' };
    }
    var result = await api('/api/v1/growth/invite', { method: 'POST' });
    return result || { invite_code: '', invite_url: '' };
  }

  // ==================== Page Data Loading ====================
  async function loadPageData(page, forceRefresh) {
    switch (page) {
      case 'dashboard':
        await loadDashboard(forceRefresh);
        break;
      case 'diagnosis':
        updateAITriggerVisibility();
        await loadDiagnosis(forceRefresh);
        break;
      case 'plan':
        updateAITriggerVisibility();
        await loadPlan(forceRefresh);
        break;
      case 'reports':
        await loadReports(forceRefresh);
        break;
      case 'growth':
        await loadGrowth(forceRefresh);
        break;
      case 'consultant':
        await loadConsultant(forceRefresh);
        break;
      case 'today':
        await loadToday(forceRefresh);
        break;
      case 'trends':
        await loadTrends(forceRefresh);
        break;
      case 'profile':
        // 加载积分余额
        loadPointsBalance();
        break;
      // 兼容旧路由
      case 'records':
      case 'tcm':
      case 'food':
      case 'nonpharma':
      case 'risk':
        await loadDiagnosis(forceRefresh);
        break;
      case 'repair':
      case 'sleep':
        await loadDashboard(forceRefresh);
        break;
    }
  }

  // ==================== Dashboard ====================
  async function loadDashboard(forceRefresh) {
    // Init charts after view is visible
    setTimeout(function () {
      initTrendChart();
      initConstitutionMiniChart();
    }, 100);

    if (state.demoMode) {
      renderDashboard(DEMO.dashboard);
      return;
    }

    if (state.cache.dashboard && !forceRefresh) {
      renderDashboard(state.cache.dashboard);
      return;
    }

    var data = await api('/api/v1/dashboard/overview');
    if (data) {
      state.cache.dashboard = data;
      renderDashboard(data);
    } else {
      renderDashboard(DEMO.dashboard);
    }
  }

  function renderDashboard(data) {
    if (!data) return;

    // Health score
    var scoreNum = document.querySelector('.score-number');
    var scoreLabel = document.querySelector('.card-highlight .badge');
    if (scoreNum && data.health_score !== undefined) {
      scoreNum.textContent = data.health_score;
    }
    if (scoreLabel && data.score_label) {
      scoreLabel.textContent = data.score_label;
      scoreLabel.className = 'badge badge-' + getScoreBadgeType(data.health_score);
    }

    // Score circle SVG arc
    var scoreCircle = document.querySelector('.score-circle svg circle:nth-child(2)');
    if (scoreCircle && data.health_score !== undefined) {
      var circumference = 2 * Math.PI * 52; // r=52
      var offset = circumference - (circumference * data.health_score / 100);
      scoreCircle.setAttribute('stroke-dasharray', circumference.toFixed(0));
      scoreCircle.setAttribute('stroke-dashoffset', offset.toFixed(0));
    }

    // Score breakdown
    if (data.score_breakdown) {
      var scoreItems = document.querySelectorAll('.score-item');
      var keys = ['physiology', 'lifestyle', 'chronic_risk'];
      var colors = ['#34c759', '#007aff', '#ff9500'];
      var labels = ['\u751F\u7406\u6307\u6807', '\u751F\u6D3B\u65B9\u5F0F', '\u6162\u75C5\u98CE\u9669'];
      scoreItems.forEach(function (item, i) {
        if (keys[i] && data.score_breakdown[keys[i]] !== undefined) {
          var dot = item.querySelector('.score-dot');
          if (dot) dot.style.background = colors[i];
          item.lastElementChild.textContent = labels[i] + ' ' + data.score_breakdown[keys[i]];
        }
      });
    }

    // Recent diagnoses
    if (data.recent_diagnoses && data.recent_diagnoses.length > 0) {
      var diagList = document.querySelector('.diagnosis-list');
      if (diagList) {
        var diagHtml = '';
        data.recent_diagnoses.forEach(function (d) {
          var iconClass = d.status || 'info';
          var iconMap = { warning: 'warning', info: 'info', success: 'success' };
          var iconEmoji = { warning: '&#9888;&#65039;', info: '&#128200;', success: '&#127793;' };
          var badgeType = { warning: 'badge-warning', info: 'badge-info', success: 'badge-success' };
          diagHtml +=
            '<div class="diagnosis-item">' +
            '  <div class="diagnosis-icon ' + (iconMap[iconClass] || 'info') + '">' + (iconEmoji[iconClass] || '&#128200;') + '</div>' +
            '  <div class="diagnosis-info">' +
            '    <p class="diagnosis-title">' + escapeHtml(d.title) + '</p>' +
            '    <p class="diagnosis-meta">' + escapeHtml(d.date) + ' \u00B7 ' + escapeHtml(d.department) + '</p>' +
            '  </div>' +
            '  <span class="badge ' + (badgeType[iconClass] || 'badge-info') + '">' + escapeHtml(d.badge) + '</span>' +
            '</div>';
        });
        diagList.innerHTML = diagHtml;
      }
    }

    // Todos
    if (data.todos && data.todos.length > 0) {
      var todoList = document.querySelector('.todo-list');
      if (todoList) {
        var todoHtml = '';
        data.todos.forEach(function (t) {
          todoHtml +=
            '<div class="todo-item">' +
            '  <input type="checkbox" class="todo-check"' + (t.done ? ' checked' : '') + '>' +
            '  <span class="todo-text' + (t.done ? ' done' : '') + '">' + escapeHtml(t.text) + '</span>' +
            '  <span class="todo-tag">' + escapeHtml(t.tag) + '</span>' +
            '</div>';
        });
        todoList.innerHTML = todoHtml;
        rebindTodoCheckboxes();
      }
    }

    // Constitution summary in dashboard
    if (data.constitution_summary) {
      var footerText = document.querySelector('#page-dashboard .card-footer-text');
      if (footerText) {
        footerText.innerHTML = '\u4E3B\u8981\u503E\u5411: <strong>' + escapeHtml(data.constitution_summary.primary) + '</strong>\uFF0C\u5EFA\u8BAE\u8C03\u7406';
      }
    }

    // Store constitution type for food/nonpharma pages
    if (data.constitution_summary) {
      state.constitutionType = data.constitution_summary.primary;
    }
  }

  // ==================== Records ====================
  async function loadRecords(forceRefresh) {
    if (state.demoMode) {
      renderRecordList(DEMO.records);
      if (DEMO.records.length > 0) {
        renderRecordDetail(DEMO.records[0]);
      }
      return;
    }

    if (state.cache.records && !forceRefresh) {
      renderRecordList(state.cache.records);
      if (state.selectedRecordId) {
        var cached = state.cache.records.find(function (r) { return r.id === state.selectedRecordId; });
        if (cached) renderRecordDetail(cached);
      } else if (state.cache.records.length > 0) {
        renderRecordDetail(state.cache.records[0]);
      }
      return;
    }

    var data = await api('/api/v1/records/');
    if (data) {
      var records = data.records || data;
      state.cache.records = records;
      renderRecordList(records);
      if (records.length > 0) {
        state.selectedRecordId = records[0].id;
        renderRecordDetail(records[0]);
      }
    } else {
      renderRecordList(DEMO.records);
      if (DEMO.records.length > 0) renderRecordDetail(DEMO.records[0]);
    }
  }

  function renderRecordList(records) {
    var listEl = document.querySelector('.report-list');
    if (!listEl) return;
    if (!records || records.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#128196;</div><div class="empty-state-text">\u6682\u65E0\u62A5\u544A\u8BB0\u5F55</div></div>';
      return;
    }
    var html = '';
    records.forEach(function (r, idx) {
      var activeClass = (state.selectedRecordId === r.id) || (!state.selectedRecordId && idx === 0) ? ' active' : '';
      var statusText = { parsed: '\u5DF2\u89E3\u6790', processing: '\u89E3\u6790\u4E2D', failed: '\u89E3\u6790\u5931\u8D25', pending: '\u5F85\u89E3\u6790' };
      var status = statusText[r.status] || r.status || '\u5DF2\u89E3\u6790';
      var tags = '';
      if (r.tags && r.tags.length > 0) {
        tags = r.tags.map(function (t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('');
      }
      html +=
        '<div class="report-item' + activeClass + '" data-record-id="' + r.id + '">' +
        '  <div class="report-date">' + escapeHtml(r.report_date) + (r.file_size ? ' \u00B7 ' + formatFileSize(r.file_size) : '') + '</div>' +
        '  <div class="report-title">' + escapeHtml(r.title) + '</div>' +
        '  <div class="report-tags">' + tags + '</div>' +
        '</div>';
    });
    listEl.innerHTML = html;

    // Rebind click handlers
    listEl.querySelectorAll('.report-item').forEach(function (item) {
      item.addEventListener('click', function () {
        listEl.querySelectorAll('.report-item').forEach(function (i) { i.classList.remove('active'); });
        item.classList.add('active');
        var recordId = parseInt(item.dataset.recordId);
        state.selectedRecordId = recordId;
        var allRecords = state.cache.records || DEMO.records;
        var record = allRecords.find(function (r) { return r.id === recordId; });
        if (record) renderRecordDetail(record);
      });
    });
  }

  function renderRecordDetail(record) {
    var detail = document.querySelector('.report-detail');
    if (!detail || !record) return;

    var statusMap = { parsed: 'processed', processing: 'processing', failed: 'failed', pending: 'pending' };
    var statusTextMap = { parsed: '\u5DF2\u89E3\u6790', processing: '\u89E3\u6790\u4E2D', failed: '\u89E3\u6790\u5931\u8D25', pending: '\u5F85\u89E3\u6790' };
    var statusClass = statusMap[record.status] || 'processed';
    var statusText = statusTextMap[record.status] || '\u5DF2\u89E3\u6790';

    var indicators = record.indicators || [];
    var indicatorsHtml = '';
    if (indicators.length > 0) {
      indicators.forEach(function (ind) {
        var cls = ind.status === 'abnormal' ? 'abnormal' : 'normal';
        var trendHtml = ind.trend ? '<div class="indicator-trend ' + (ind.status === 'abnormal' ? 'up' : '') + '">' + escapeHtml(ind.trend) + '</div>' : '';
        indicatorsHtml +=
          '<div class="indicator-card ' + cls + '">' +
          '  <div class="indicator-name">' + escapeHtml(ind.name) + '</div>' +
          '  <div class="indicator-value">' + escapeHtml(ind.value) + ' <small>' + escapeHtml(ind.unit) + '</small></div>' +
          '  <div class="indicator-range">\u53C2\u8003: ' + escapeHtml(ind.ref) + '</div>' +
          trendHtml +
          '</div>';
      });
    } else {
      indicatorsHtml = '<div class="empty-state"><div class="empty-state-text">\u6682\u65E0\u6307\u6807\u6570\u636E</div></div>';
    }

    detail.innerHTML =
      '<div class="report-detail-header">' +
      '  <h2>' + escapeHtml(record.title) + '</h2>' +
      '  <span class="report-status ' + statusClass + '">' + escapeHtml(statusText) + '</span>' +
      '</div>' +
      '<div class="indicators-grid">' + indicatorsHtml + '</div>' +
      '<div class="report-actions">' +
      '  <button class="btn btn-primary" id="btn-ai-analysis">\u67E5\u770BAI\u5206\u6790</button>' +
      '  <button class="btn btn-secondary">\u5BFC\u51FAPDF</button>' +
      '  <button class="btn btn-ghost">\u5206\u4EAB\u7ED9\u987E\u95EE</button>' +
      '</div>';

    // Bind AI analysis button
    var aiBtn = document.getElementById('btn-ai-analysis');
    if (aiBtn) {
      aiBtn.addEventListener('click', async function () {
        aiBtn.classList.add('loading');
        var result = await api('/api/v1/diagnosis/analyze', {
          method: 'POST',
          body: JSON.stringify({ record_id: record.id })
        });
        aiBtn.classList.remove('loading');
        if (result) {
          showSuccessToast('AI\u8BCA\u65AD\u5DF2\u5B8C\u6210\uFF0C\u8BF7\u67E5\u770B\u8BCA\u65AD\u7ED3\u679C');
        }
      });
    }
  }

  // ==================== TCM Constitution ====================
  async function loadTCM(forceRefresh) {
    setTimeout(function () {
      initConstitutionRadarChart();
    }, 100);

    if (state.demoMode) {
      renderTCM(DEMO.constitution);
      return;
    }

    if (state.cache.tcm && !forceRefresh) {
      renderTCM(state.cache.tcm);
      return;
    }

    var data = await api('/api/v1/tcm/constitution');
    if (data) {
      state.cache.tcm = data;
      state.constitutionType = data.constitution_type;
      state.constitutionScores = data.constitution_scores;
      renderTCM(data);
    } else {
      renderTCM(DEMO.constitution);
    }
  }

  function renderTCM(data) {
    if (!data) return;

    // Update constitution result text
    var resultType = document.querySelector('.result-type');
    var resultPercent = document.querySelector('.result-percent');
    var resultSecondary = document.querySelector('.result-secondary span');
    if (resultType) resultType.textContent = data.constitution_type || '\u672A\u77E5';
    if (resultPercent) resultPercent.textContent = '\u5339\u914D\u5EA6 ' + (data.match_score || 0) + '%';
    if (resultSecondary && data.secondary_types) {
      resultSecondary.textContent = '\u6B21\u8981\u503E\u5411: ' + data.secondary_types.join('\u3001');
    }

    // Update advice if available
    if (data.advice) {
      var adviceCards = document.querySelectorAll('.advice-card');
      var adviceKeys = ['symptoms', 'diet', 'lifestyle', 'emotional'];
      adviceCards.forEach(function (card, i) {
        var list = card.querySelector('ul');
        if (list && data.advice[adviceKeys[i]]) {
          var items = data.advice[adviceKeys[i]];
          if (Array.isArray(items)) {
            list.innerHTML = items.map(function (item) { return '<li>' + escapeHtml(item) + '</li>'; }).join('');
          }
        }
      });
    }
  }

  // ==================== Food Therapy ====================
  async function loadFood(forceRefresh) {
    var container = document.querySelector('.recipe-grid');
    if (!container) return;

    showSkeletonCards(container, 4);

    var constitutionType = state.constitutionType;

    // If we don't have constitution type yet, try to fetch it
    if (!constitutionType && !state.demoMode) {
      var tcmData = await api('/api/v1/tcm/constitution', { silent: true });
      if (tcmData && tcmData.constitution_type) {
        constitutionType = tcmData.constitution_type;
        state.constitutionType = constitutionType;
      }
    }

    if (!constitutionType) {
      constitutionType = '\u6C14\u865A\u8D28'; // Default fallback
    }

    // Update page description
    var descEl = document.querySelector('#page-food .page-desc');
    if (descEl) {
      descEl.textContent = '\u6839\u636E\u60A8\u7684' + constitutionType + '\u503E\u5411\uFF0C\u63A8\u8350\u4EE5\u4E0B\u98DF\u7597\u65B9';
    }

    if (state.demoMode) {
      renderFoodRecipes(DEMO.foodRecipes);
      return;
    }

    if (state.cache.food && !forceRefresh) {
      renderFoodRecipes(state.cache.food);
      return;
    }

    var data = await api('/api/v1/knowledge/food-therapy/recommend', {
      method: 'POST',
      body: JSON.stringify({ constitution_type: constitutionType })
    });

    if (data) {
      var recipes = data.recipes || data;
      state.cache.food = recipes;
      renderFoodRecipes(recipes);
    } else {
      renderFoodRecipes(DEMO.foodRecipes);
    }
  }

  function renderFoodRecipes(recipes) {
    var container = document.querySelector('.recipe-grid');
    if (!container) return;
    if (!recipes || recipes.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#129516;</div><div class="empty-state-text">\u6682\u65E0\u63A8\u8350\u98DF\u7597\u65B9\u6848</div></div>';
      return;
    }
    var html = '';
    recipes.forEach(function (r) {
      var featuredClass = r.featured ? ' featured' : '';
      var gradient = r.gradient || 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)';
      var emoji = r.emoji || '&#129379;';
      var tagHtml = r.featured ? '<span class="recipe-tag">\u63A8\u8350</span>' : '';
      var ingredientsHtml = '';
      if (r.ingredients && r.ingredients.length > 0) {
        ingredientsHtml = '<div class="recipe-ingredients">' +
          r.ingredients.map(function (ing) { return '<span class="ingredient">' + escapeHtml(ing) + '</span>'; }).join('') +
          '</div>';
      }
      html +=
        '<div class="recipe-card' + featuredClass + '">' +
        '  <div class="recipe-image" style="background: ' + gradient + ';">' +
        '    <span class="recipe-emoji">' + emoji + '</span>' +
        tagHtml +
        '  </div>' +
        '  <div class="recipe-body">' +
        '    <h3>' + escapeHtml(r.name) + '</h3>' +
        '    <p class="recipe-effect">' + escapeHtml(r.effect) + '</p>' +
        ingredientsHtml +
        '    <div class="recipe-method"><strong>\u505A\u6CD5:</strong> ' + escapeHtml(r.method) + '</div>' +
        '    <div class="recipe-meta">' +
        '      <span>&#128197; ' + escapeHtml(r.frequency) + '</span>' +
        '      <span>&#9200; ' + escapeHtml(r.duration) + '</span>' +
        '    </div>' +
        '  </div>' +
        '</div>';
    });
    container.innerHTML = html;
  }

  // ==================== Non-Pharma ====================
  async function loadNonPharma(forceRefresh) {
    var container = document.querySelector('.nonpharma-grid');
    if (!container) return;

    // For non-pharma, we use the existing static content as a rich fallback
    // and only update from API if available
    if (state.demoMode) return;

    if (state.cache.nonpharma && !forceRefresh) return;

    var constitutionType = state.constitutionType || '\u6C14\u865A\u8D28';

    var data = await api('/api/v1/knowledge/non-pharma/recommend', {
      method: 'POST',
      body: JSON.stringify({ constitution_type: constitutionType }),
      silent: true
    });

    if (data) {
      state.cache.nonpharma = data;
      renderNonPharma(data);
    }
    // If no API data, keep the existing static HTML content (it's already good demo content)
  }

  function renderNonPharma(data) {
    if (!data || !data.treatments) return;
    var container = document.querySelector('.nonpharma-grid');
    if (!container) return;
    var html = '';
    var iconMap = ['&#128294;', '&#129496;', '&#127807;', '&#127748;'];
    data.treatments.forEach(function (t, idx) {
      var pointsHtml = '';
      if (t.points && t.points.length > 0) {
        pointsHtml = '<div class="nonpharma-detail">' +
          t.points.map(function (p) {
            return '<div class="point-item">' +
              '<span class="point-name">' + escapeHtml(p.name) + '</span>' +
              (p.location ? '<span class="point-loc">' + escapeHtml(p.location) + '</span>' : '') +
              '<span class="point-effect">' + escapeHtml(p.effect) + '</span>' +
              '</div>';
          }).join('') +
          '</div>';
      }
      var sectionsHtml = '';
      if (t.sections && t.sections.length > 0) {
        sectionsHtml = '<div class="baduanjin-sections">' +
          t.sections.map(function (s, si) {
            return '<div class="section-item"><span class="section-num">' + (si + 1) + '</span><span>' + escapeHtml(s) + '</span></div>';
          }).join('') +
          '</div>';
      }
      html +=
        '<div class="nonpharma-card">' +
        '  <div class="nonpharma-icon">' + (iconMap[idx] || '&#129496;') + '</div>' +
        '  <h3>' + escapeHtml(t.name) + '</h3>' +
        '  <p class="nonpharma-desc">' + escapeHtml(t.description) + '</p>' +
        pointsHtml + sectionsHtml +
        '  <div class="nonpharma-guide"><strong>\u5EFA\u8BAE:</strong> ' + escapeHtml(t.guide || '') + '</div>' +
        '</div>';
    });
    container.innerHTML = html;
  }

  // ==================== Risk Assessment ====================
  async function loadRisk(forceRefresh) {
    if (state.demoMode) return; // Keep existing static risk content

    if (state.cache.risk && !forceRefresh) return;

    var data = await api('/api/v1/dashboard/risk-assessment', {
      method: 'POST',
      silent: true
    });

    if (data) {
      state.cache.risk = data;
      renderRisk(data);
    }
  }

  function renderRisk(data) {
    if (!data || !data.risks) return;
    // The risk page has complex SVG gauges that are hard to update dynamically.
    // For now, we update the risk percentages and badges if data is available.
    var riskCards = document.querySelectorAll('#page-risk .card');
    data.risks.forEach(function (risk, idx) {
      if (idx >= riskCards.length) return;
      var card = riskCards[idx];
      var badge = card.querySelector('.badge');
      var gaugeText = card.querySelectorAll('svg text');
      if (badge) {
        badge.textContent = risk.level || '\u4E2D\u5371';
      }
      if (gaugeText.length >= 1) {
        gaugeText[0].textContent = (risk.risk_score || 0) + '%';
      }
      // Update factors
      var factorList = card.querySelector('.factor-list');
      if (factorList && risk.factors) {
        var fhtml = '';
        risk.factors.forEach(function (f) {
          var cls = f.risk ? 'warning' : 'normal';
          var badge = f.risk ? '<span class="factor-badge">+</span>' : '<span class="factor-badge ok">&#10003;</span>';
          fhtml += '<div class="factor-item ' + cls + '"><span>' + escapeHtml(f.label) + '</span>' + badge + '</div>';
        });
        factorList.innerHTML = fhtml;
      }
    });
  }

  // ==================== Reports Center ====================
  async function loadReports(forceRefresh) {
    if (state.demoMode) {
      renderReports(DEMO.reports);
      return;
    }
    // Fallback to demo since reports API is not yet implemented
    renderReports(DEMO.reports);
  }

  function renderReports(data) {
    if (!data) return;
    var list = document.querySelector('.report-list');
    if (!list) return;
    var typeColors = { checkup: '#2563eb', genetic: '#7c3aed', imaging: '#0891b2', lab: '#ea580c', tcm: '#0d8a6a' };
    var typeIcons = { clipboard: '&#128203;', dna: '&#129516;', scan: '&#129656;', test_tube: '&#129514;', leaf: '&#127793;' };
    list.innerHTML = data.map(function (r) {
      var color = typeColors[r.type] || '#64748b';
      var statusLabel = r.status === 'parsed' ? '\u5DF2\u89E3\u6790' : r.status === 'pending' ? '\u5F85\u89E3\u6790' : '\u89E3\u6790\u4E2D';
      var statusClass = r.status === 'parsed' ? 'success' : r.status === 'pending' ? 'warning' : 'info';
      return '<div class="report-file-card" data-type="' + r.type + '">' +
        '<div class="report-file-icon" style="background:' + color + '15;color:' + color + '">' +
        (typeIcons[r.icon] || '&#128196;') + '</div>' +
        '<div class="report-file-info">' +
        '<div class="report-file-name">' + escapeHtml(r.name) + '</div>' +
        '<div class="report-file-meta"><span>' + r.date + '</span><span class="dot">·</span><span>' + r.size + '</span></div>' +
        '</div>' +
        '<div class="report-file-tags">' +
        '<span class="report-type-tag" style="background:' + color + '12;color:' + color + ';border:1px solid ' + color + '30">' + escapeHtml(r.typeName) + '</span>' +
        '<span class="report-status-tag ' + statusClass + '">' + statusLabel + '</span>' +
        '</div>' +
        '<div class="report-file-actions">' +
        '<button class="btn btn-ghost btn-sm" onclick="showToast(\'\u67E5\u770B\u62A5\u544A\u529F\u80FD\u5F00\u53D1\u4E2D\',\'info\')">\u67E5\u770B</button>' +
        '<button class="btn btn-ghost btn-sm text-danger" onclick="showToast(\'\u5DF2\u5220\u9664\',\'success\')">\u5220\u9664</button>' +
        '</div></div>';
    }).join('');
    // Filter buttons
    var filterBtns = document.querySelectorAll('.report-filter-btn');
    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var filter = btn.getAttribute('data-filter');
        var cards = document.querySelectorAll('.report-file-card');
        cards.forEach(function (card) {
          if (filter === 'all' || card.getAttribute('data-type') === filter) {
            card.style.display = '';
          } else {
            card.style.display = 'none';
          }
        });
      });
    });
    // Upload area
    var uploadArea = document.querySelector('.upload-area-large');
    if (uploadArea) {
      uploadArea.addEventListener('click', function () {
        showToast('\u4E0A\u4F20\u529F\u80FD\u5F00\u53D1\u4E2D\uFF0C\u5F53\u524D\u4EC5\u652F\u6301\u6F14\u793A\u6A21\u5F0F', 'info');
      });
    }
  }

  // ==================== Cell Repair Dashboard ====================
  async function loadRepair(forceRefresh) {
    if (state.demoMode) {
      renderRepair(DEMO.repair);
      return;
    }
    // For now, fallback to demo data even in non-demo mode
    // since the backend API for repair data is not yet implemented
    renderRepair(DEMO.repair);
  }

  function renderRepair(data) {
    if (!data) return;
    // Update score circle
    var scoreCircle = document.getElementById('repair-score-circle');
    if (scoreCircle) {
      var circumference = 389.6;
      var offset = circumference * (1 - data.score / 100);
      var color = data.score >= 80 ? '#0d8a6a' : data.score >= 60 ? '#f59e0b' : '#dc2626';
      scoreCircle.innerHTML =
        '<svg viewBox="0 0 140 140" width="140" height="140">' +
        '<circle cx="70" cy="70" r="62" fill="none" stroke="#e8ecf1" stroke-width="10"/>' +
        '<circle cx="70" cy="70" r="62" fill="none" stroke="' + color + '" stroke-width="10" stroke-dasharray="' + circumference + '" stroke-dashoffset="' + offset + '" stroke-linecap="round" transform="rotate(-90 70 70)"/>' +
        '<text x="70" y="65" text-anchor="middle" dominant-baseline="central" font-size="36" font-weight="700" fill="' + color + '">' + data.score + '</text>' +
        '<text x="70" y="88" text-anchor="middle" font-size="11" fill="#6b7280">修复评分</text>' +
        '</svg>';
    }
    // Update score info
    var scoreStatus = document.querySelector('.repair-score-status');
    if (scoreStatus) {
      scoreStatus.textContent = data.status + ' — 击败了 ' + data.percentile + '% 的同体质用户';
      scoreStatus.style.color = data.score >= 80 ? '#0d8a6a' : data.score >= 60 ? '#f59e0b' : '#dc2626';
    }
    var repairAge = document.querySelector('.repair-age strong');
    if (repairAge) repairAge.textContent = data.repairAge + '岁';
    var trendEl = document.querySelector('.repair-score-trend');
    if (trendEl) {
      var trendClass = data.scoreTrend >= 0 ? 'trend-up' : 'trend-down';
      var trendIcon = data.scoreTrend >= 0 ? '&#9650;' : '&#9660;';
      trendEl.innerHTML = '<span class="' + trendClass + '">' + trendIcon + ' ' + (data.scoreTrend >= 0 ? '+' : '') + data.scoreTrend + '分</span> 较上周';
    }
    // Update damage mode tags
    var damageTags = document.querySelector('.damage-mode-tags');
    if (damageTags && data.damageModes) {
      damageTags.innerHTML = data.damageModes.map(function (m) {
        var cls = m.level === 'primary' ? 'primary' : 'secondary';
        return '<span class="damage-tag ' + cls + '">' + escapeHtml(m.name) + '</span>';
      }).join('');
    }
    // Update pillar cards
    var pillarCards = document.querySelectorAll('.pillar-card');
    data.dailyPillars.forEach(function (p, idx) {
      if (idx >= pillarCards.length) return;
      var card = pillarCards[idx];
      var scoreEl = card.querySelector('.pillar-score');
      var bar = card.querySelector('.pillar-bar');
      var detail = card.querySelector('.pillar-detail');
      var priority = card.querySelector('.pillar-priority');
      if (scoreEl) scoreEl.textContent = p.score;
      if (bar) {
        bar.style.width = p.score + '%';
        var barColor = p.score >= 70 ? 'linear-gradient(90deg,#0d8a6a,#10b981)' : p.score >= 50 ? 'linear-gradient(90deg,#f59e0b,#fbbf24)' : 'linear-gradient(90deg,#dc2626,#f87171)';
        bar.style.background = barColor;
      }
      if (detail) detail.textContent = p.detail;
      if (priority) {
        priority.textContent = p.priority === 'high' ? '优先修复' : p.priority === 'medium' ? '持续优化' : '保持现状';
        priority.className = 'pillar-priority ' + p.priority;
      }
    });
    // Update plan timeline
    var planTimeline = document.querySelector('.plan-timeline');
    if (planTimeline && data.plan) {
      planTimeline.innerHTML = data.plan.map(function (item) {
        return '<div class="plan-item">' +
          '<div class="plan-time">' + escapeHtml(item.time) + '</div>' +
          '<div class="plan-content">' +
          '<div class="plan-title">' + escapeHtml(item.title) + '</div>' +
          '<div class="plan-desc">' + escapeHtml(item.desc) + '</div>' +
          '<div class="plan-tag ' + item.tag + '">' + escapeHtml(item.tagLabel) + '</div>' +
          '</div></div>';
      }).join('');
    }
    // Draw trend chart
    drawRepairTrend(data.trend);
  }

  function drawRepairTrend(trend) {
    var container = document.getElementById('repair-trend-chart');
    if (!container || !trend) return;
    var w = container.clientWidth || 600;
    var h = 220;
    var pad = { top: 20, right: 30, bottom: 30, left: 40 };
    var cw = w - pad.left - pad.right;
    var ch = h - pad.top - pad.bottom;
    var n = trend.dates.length;
    var maxScore = 100;
    var maxHrv = Math.max.apply(null, trend.hrv) * 1.2;

    function x(i) { return pad.left + (i / (n - 1)) * cw; }
    function yScore(v) { return pad.top + ch - (v / maxScore) * ch; }
    function yHrv(v) { return pad.top + ch - (v / maxHrv) * ch; }

    function pathLine(vals, yfn) {
      var d = '';
      for (var i = 0; i < vals.length; i++) {
        d += (i === 0 ? 'M' : 'L') + x(i) + ',' + yfn(vals[i]);
      }
      return d;
    }

    var svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="100%" style="overflow:visible">';
    // Grid lines
    for (var g = 0; g <= 4; g++) {
      var gy = pad.top + (g / 4) * ch;
      svg += '<line x1="' + pad.left + '" y1="' + gy + '" x2="' + (pad.left + cw) + '" y2="' + gy + '" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>';
      svg += '<text x="' + (pad.left - 8) + '" y="' + (gy + 4) + '" text-anchor="end" font-size="10" fill="#94a3b8">' + (100 - g * 25) + '</text>';
    }
    // Score line
    svg += '<path d="' + pathLine(trend.scores, yScore) + '" fill="none" stroke="#0d8a6a" stroke-width="2.5" stroke-linecap="round"/>';
    // Score dots
    for (var i = 0; i < trend.scores.length; i++) {
      svg += '<circle cx="' + x(i) + '" cy="' + yScore(trend.scores[i]) + '" r="4" fill="#0d8a6a"/>';
      svg += '<text x="' + x(i) + '" y="' + (yScore(trend.scores[i]) - 10) + '" text-anchor="middle" font-size="10" fill="#0d8a6a" font-weight="600">' + trend.scores[i] + '</text>';
    }
    // X labels
    for (var i = 0; i < trend.dates.length; i++) {
      svg += '<text x="' + x(i) + '" y="' + (h - 8) + '" text-anchor="middle" font-size="10" fill="#64748b">' + trend.dates[i] + '</text>';
    }
    // Legend
    svg += '<g transform="translate(' + (pad.left + 10) + ',' + (pad.top - 5) + '")>';
    svg += '<circle cx="0" cy="0" r="4" fill="#0d8a6a"/><text x="10" y="4" font-size="11" fill="#0f172a">修复评分</text>';
    svg += '</g>';
    svg += '</svg>';
    container.innerHTML = svg;
  }

  // ==================== Sleep Module ====================
  var sleepTimers = { baduanjin: null, moxa: null, moxaRemaining: 900 };

  async function loadSleep(forceRefresh) {
    if (state.demoMode) {
      renderSleep(DEMO.sleep);
    } else {
      // Backend API not yet implemented, use demo data
      renderSleep(DEMO.sleep);
    }
  }

  function renderSleep(data) {
    // Update sleep score circle
    var scoreCircle = document.querySelector('.sleep-score-circle svg circle:last-of-type');
    if (scoreCircle) {
      var circumference = 2 * Math.PI * 85;
      var offset = circumference - (data.score / 100) * circumference;
      scoreCircle.setAttribute('stroke-dashoffset', offset);
    }
    var scoreText = document.querySelector('.sleep-score-circle text:first-of-type');
    if (scoreText) scoreText.textContent = data.score;
    var scoreLabel = document.querySelector('.sleep-score-circle text:last-of-type');
    if (scoreLabel) scoreLabel.textContent = data.scoreLabel;

    // Render tones
    var toneGrid = document.querySelector('.tone-grid');
    if (toneGrid) {
      toneGrid.innerHTML = data.tones.map(function(t, i) {
        return '<div class="tone-card" data-tone="' + i + '" style="border-color:' + (t.active ? t.color : 'var(--rule)') + '">' +
          '<span class="tone-name">' + t.name + '</span>' +
          '<span class="tone-effect">' + t.effect + '</span>' +
          '<div class="tone-progress"><div class="tone-progress-bar" style="width:' + (t.active ? '35%' : '0%') + ';background:' + t.color + '"></div></div>' +
          '<div class="tone-controls"><button class="tone-btn play-btn">' + (t.active ? '&#9646;&#9646;' : '&#9654;') + '</button></div>' +
          '</div>';
      }).join('');
      toneGrid.querySelectorAll('.tone-card').forEach(function(card) {
        card.addEventListener('click', function() {
          var idx = parseInt(this.dataset.tone);
          var wasActive = data.tones[idx].active;
          data.tones.forEach(function(t) { t.active = false; });
          data.tones[idx].active = !wasActive;
          renderSleep(data);
          showToast(wasActive ? '已停止播放' : '正在播放 ' + data.tones[idx].name + '音乐', 'info');
        });
      });
    }

    // Render checklist
    var checklistGrid = document.querySelector('.checklist-grid');
    if (checklistGrid) {
      checklistGrid.innerHTML = data.checklist.map(function(item) {
        return '<label class="checklist-item' + (item.checked ? ' checked' : '') + '">' +
          '<input type="checkbox" ' + (item.checked ? 'checked' : '') + ' data-id="' + item.id + '">' +
          '<span class="cl-text">' + item.text + '</span></label>';
      }).join('');
      checklistGrid.querySelectorAll('.checklist-item input').forEach(function(cb) {
        cb.addEventListener('change', function() {
          var id = this.dataset.id;
          var item = data.checklist.find(function(c) { return c.id === id; });
          if (item) item.checked = this.checked;
          this.parentElement.classList.toggle('checked', this.checked);
          var done = data.checklist.filter(function(c) { return c.checked; }).length;
          if (done === data.checklist.length) {
            showToast('睡前准备全部完成！祝您好梦', 'success');
          }
        });
      });
    }

    // Draw sleep trend chart
    var container = document.getElementById('sleep-trend-chart');
    if (container && data.trend) {
      drawSleepTrend(data.trend);
    }
  }

  function drawSleepTrend(trend) {
    var container = document.getElementById('sleep-trend-chart');
    if (!container) return;
    var W = container.clientWidth || 600;
    var H = container.clientHeight || 240;
    var pad = { top: 20, right: 20, bottom: 30, left: 40 };
    var cw = W - pad.left - pad.right;
    var ch = H - pad.top - pad.bottom;
    var scores = trend.scores;
    var dates = trend.dates;
    var maxS = 100, minS = 0;

    var points = scores.map(function(s, i) {
      return {
        x: pad.left + (i / (scores.length - 1)) * cw,
        y: pad.top + ch - ((s - minS) / (maxS - minS)) * ch
      };
    });

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:' + H + 'px">';
    // Grid
    for (var g = 0; g <= 4; g++) {
      var gy = pad.top + (g / 4) * ch;
      svg += '<line x1="' + pad.left + '" y1="' + gy + '" x2="' + (W - pad.right) + '" y2="' + gy + '" stroke="#e8ecf1" stroke-width="1"/>';
      svg += '<text x="' + (pad.left - 8) + '" y="' + (gy + 4) + '" text-anchor="end" font-size="11" fill="#6b7280">' + Math.round(maxS - (g / 4) * (maxS - minS)) + '</text>';
    }
    // Target line
    var targetY = pad.top + ch - ((70 - minS) / (maxS - minS)) * ch;
    svg += '<line x1="' + pad.left + '" y1="' + targetY + '" x2="' + (W - pad.right) + '" y2="' + targetY + '" stroke="#ff9500" stroke-width="1" stroke-dasharray="4,4"/>';
    svg += '<text x="' + (W - pad.right + 4) + '" y="' + (targetY + 4) + '" font-size="10" fill="#ff9500">目标70</text>';
    // Area fill
    var areaPath = 'M' + points[0].x + ',' + points[0].y;
    points.forEach(function(p) { areaPath += ' L' + p.x + ',' + p.y; });
    areaPath += ' L' + points[points.length - 1].x + ',' + (pad.top + ch) + ' L' + points[0].x + ',' + (pad.top + ch) + ' Z';
    svg += '<path d="' + areaPath + '" fill="rgba(13,138,106,0.1)"/>';
    // Line
    var linePath = 'M' + points[0].x + ',' + points[0].y;
    points.forEach(function(p, i) { if (i > 0) linePath += ' L' + p.x + ',' + p.y; });
    svg += '<path d="' + linePath + '" fill="none" stroke="#0d8a6a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
    // Dots + date labels
    points.forEach(function(p, i) {
      svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="4" fill="#0d8a6a" stroke="white" stroke-width="2"/>';
      svg += '<text x="' + p.x + '" y="' + (pad.top + ch + 18) + '" text-anchor="middle" font-size="10" fill="#6b7280">' + dates[i] + '</text>';
    });
    svg += '</svg>';
    container.innerHTML = svg;
  }

  // ==================== Fusion Chain Diagnosis Page ====================
  var FUSION_DEMO = null;

  // AI diagnosis polling helper: poll /api/v1/diagnosis/agent-status/{task_id} every 2s, max 15 times (30s)
  async function pollAgentStatus(taskId) {
    var maxAttempts = 15;
    var interval = 2000;
    for (var i = 0; i < maxAttempts; i++) {
      try {
        await new Promise(function(resolve) { setTimeout(resolve, interval); });
        var resp = await api('/api/v1/diagnosis/agent-status/' + taskId);
        if (resp && resp.status === 'completed' && resp.data) {
          return resp.data;
        }
        if (resp && resp.status === 'failed') {
          console.warn('AI diagnosis task failed:', resp.error);
          return null;
        }
        // status === 'pending' or 'running', continue polling
      } catch(e) {
        console.warn('pollAgentStatus error (attempt ' + (i+1) + '):', e);
      }
    }
    console.warn('pollAgentStatus timed out after ' + (maxAttempts * interval / 1000) + 's');
    return null;
  }

  // Show/hide AI trigger buttons based on demoMode
  function updateAITriggerVisibility() {
    var diagTrigger = document.getElementById('ai-analysis-trigger');
    var planTrigger = document.getElementById('ai-plan-trigger');
    var freqSection = document.getElementById('frequency-prescription-section');
    if (!state.demoMode) {
      if (diagTrigger) diagTrigger.style.display = 'block';
      if (planTrigger) planTrigger.style.display = 'block';
      if (freqSection) freqSection.style.display = 'block';
    }
  }

  // Global: trigger AI diagnosis from button click
  async function triggerAIDiagnosis() {
    var statusEl = document.getElementById('ai-analysis-status');
    var progressEl = document.getElementById('ai-analysis-progress');
    var btnEl = document.getElementById('btn-ai-analysis');
    if (btnEl) btnEl.disabled = true;
    if (statusEl) statusEl.style.display = 'block';
    if (progressEl) progressEl.textContent = '正在提交分析任务...';

    try {
      var agentResp = await api('/api/v1/diagnosis/agent-run', {
        method: 'POST',
        body: JSON.stringify({
          genes: state.userGeneVariants || [],
          lab_results: state.userLabResults || [],
          tcm_symptoms: state.userTcmSymptoms || []
        })
      });
      if (agentResp && agentResp.task_id) {
        if (progressEl) progressEl.textContent = '任务已提交，AI 正在深度分析中（预计 10-30 秒）...';
        var chainData = await pollAgentStatus(agentResp.task_id);
        if (chainData) {
          FUSION_DEMO = chainData;
          renderFusionChain(FUSION_DEMO);
          if (statusEl) statusEl.style.display = 'none';
          if (progressEl) progressEl.textContent = '';
          if (btnEl) btnEl.disabled = false;
          return;
        }
        if (progressEl) progressEl.textContent = 'AI 分析超时，已回退到标准分析数据。';
      } else {
        if (progressEl) progressEl.textContent = 'AI 服务暂不可用，已回退到标准分析。';
      }
    } catch(e) {
      console.warn('triggerAIDiagnosis failed:', e);
      if (progressEl) progressEl.textContent = 'AI 分析出错，已回退到标准分析。';
    }
    if (btnEl) btnEl.disabled = false;
  }

  // Global: trigger AI plan generation from button click
  async function triggerAIPlan() {
    var statusEl = document.getElementById('ai-plan-status');
    var progressEl = document.getElementById('ai-plan-progress');
    var btnEl = document.getElementById('btn-ai-plan');
    if (btnEl) btnEl.disabled = true;
    if (statusEl) statusEl.style.display = 'block';
    if (progressEl) progressEl.textContent = '正在提交生成任务...';

    try {
      var agentResp = await api('/api/v1/diagnosis/agent-run', {
        method: 'POST',
        body: JSON.stringify({
          genes: state.userGeneVariants || [],
          lab_results: state.userLabResults || [],
          tcm_symptoms: state.userTcmSymptoms || []
        })
      });
      if (agentResp && agentResp.task_id) {
        if (progressEl) progressEl.textContent = '任务已提交，AI 正在生成个性化方案（预计 10-30 秒）...';
        var chainData = await pollAgentStatus(agentResp.task_id);
        if (chainData) {
          FUSION_DEMO = chainData;
          renderPlanFromFusion(FUSION_DEMO);
          if (statusEl) statusEl.style.display = 'none';
          if (progressEl) progressEl.textContent = '';
          if (btnEl) btnEl.disabled = false;
          return;
        }
        if (progressEl) progressEl.textContent = 'AI 方案生成超时，已回退到标准方案。';
      } else {
        if (progressEl) progressEl.textContent = 'AI 服务暂不可用，已回退到标准方案。';
      }
    } catch(e) {
      console.warn('triggerAIPlan failed:', e);
      if (progressEl) progressEl.textContent = 'AI 方案生成出错，已回退到标准方案。';
    }
    if (btnEl) btnEl.disabled = false;
  }

  // Global: trigger frequency prescription generation
  async function triggerFrequencyPrescription() {
    var statusEl = document.getElementById('frequency-prescription-status');
    var progressEl = document.getElementById('frequency-prescription-progress');
    var resultEl = document.getElementById('frequency-prescription-result');
    var btnEl = document.getElementById('btn-frequency-prescription');
    if (btnEl) btnEl.disabled = true;
    if (statusEl) statusEl.style.display = 'block';
    if (resultEl) resultEl.style.display = 'none';
    if (progressEl) progressEl.textContent = '正在分析证候与通路数据...';

    try {
      // 使用当前分析数据生成频率方案
      var diagnosisData = FUSION_DEMO || getFusionDemoData();
      var resp = await api('/api/v1/frequency/prescription', {
        method: 'POST',
        body: JSON.stringify({
          diagnosis_data: diagnosisData,
          tcm_symptoms: state.tcmSymptoms || []
        })
      });
      if (resp && resp.prescription) {
        if (progressEl) progressEl.textContent = '频率修复清单生成好了！';
        renderFrequencyPrescription(resp.prescription, resultEl);
        if (resultEl) resultEl.style.display = 'block';
      } else {
        if (progressEl) progressEl.textContent = '清单生成失败，稍后再试。';
      }
    } catch(e) {
      console.warn('triggerFrequencyPrescription failed:', e);
      if (progressEl) progressEl.textContent = '频率清单生成出错：' + (e.message || '未知错误');
    }
    if (btnEl) btnEl.disabled = false;
  }

  function renderFrequencyPrescription(prescription, container) {
    if (!container) return;
    var daily = prescription.daily_plan || {};
    var tracks = prescription.tracks || [];
    var html = '<div style="background:rgba(139,92,246,0.04);border:1px solid rgba(139,92,246,0.12);border-radius:12px;padding:1rem">';
    html += '<div style="font-size:0.9rem;font-weight:600;color:#8b5cf6;margin-bottom:0.5rem">你的频率修复清单</div>';
    html += '<div style="font-size:0.8rem;color:var(--muted);line-height:1.5;margin-bottom:0.75rem">' + (prescription.rationale || '').substring(0, 120) + '...</div>';

    // 每日建议
    html += '<div style="margin-bottom:0.75rem">';
    html += '<div style="font-size:0.8rem;font-weight:600;color:var(--ink);margin-bottom:0.4rem">今天可以试试</div>';
    Object.keys(daily).forEach(function(key) {
      var slot = daily[key];
      if (slot && slot.track) {
        html += '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.5rem;background:#fff;border-radius:8px;margin-bottom:0.4rem">';
        html += '<div style="width:8px;height:8px;border-radius:50%;background:#8b5cf6"></div>';
        html += '<div style="flex:1">';
        html += '<div style="font-size:0.8rem;font-weight:600">' + slot.track.title + ' <span style="font-weight:400;color:var(--muted)">' + slot.track.subtitle + '</span></div>';
        html += '<div style="font-size:0.75rem;color:var(--muted)">' + slot.time + ' · ' + slot.duration + '分钟 · ' + slot.purpose + '</div>';
        html += '</div></div>';
      }
    });
    html += '</div>';

    // 曲目标签
    html += '<div style="margin-bottom:0.75rem">';
    html += '<div style="font-size:0.8rem;font-weight:600;color:var(--ink);margin-bottom:0.4rem">推荐曲目 (' + tracks.length + '首)</div>';
    html += '<div style="display:flex;gap:0.4rem;flex-wrap:wrap">';
    tracks.slice(0, 6).forEach(function(t) {
      html += '<span style="font-size:0.75rem;padding:0.25rem 0.6rem;background:rgba(139,92,246,0.08);color:#8b5cf6;border-radius:6px">' + t.title + '</span>';
    });
    html += '</div></div>';

    // 小程序同步提示
    html += '<div style="font-size:0.75rem;color:var(--muted);padding:0.6rem;background:rgba(139,92,246,0.06);border-radius:8px">';
    html += '清单已生成，可在「舒服的频率」小程序中扫码同步。建议连续使用7天以上让身体慢慢适应。';
    html += '</div>';

    html += '</div>';
    container.innerHTML = html;
  }

  async function loadDiagnosis(forceRefresh) {
    // Demo mode: use built-in demo data
    if (state.demoMode === true) {
      FUSION_DEMO = getFusionDemoData();
      renderFusionChain(FUSION_DEMO);
      return;
    }

    // Real user mode: try AI diagnosis endpoint first
    try {
      var agentResp = await api('/api/v1/diagnosis/agent-run', {
        method: 'POST',
        body: JSON.stringify({
          genes: state.userGeneVariants || [],
          lab_results: state.userLabResults || [],
          tcm_symptoms: state.userTcmSymptoms || []
        })
      });
      if (agentResp && agentResp.task_id) {
        var chainData = await pollAgentStatus(agentResp.task_id);
        if (chainData) {
          FUSION_DEMO = chainData;
          renderFusionChain(FUSION_DEMO);
          return;
        }
      }
    } catch(e) {
      console.warn('AI diagnosis failed, falling back to existing logic', e);
    }

    // Fallback: try existing fusion/chain endpoint
    try {
      var res = await fetch('/api/v1/fusion/chain');
      if (res.ok) {
        var result = await res.json();
        FUSION_DEMO = result.data || result;
        renderFusionChain(FUSION_DEMO);
        return;
      }
    } catch(e) { /* fallback to built-in demo */ }

    // Built-in demo data fallback
    FUSION_DEMO = getFusionDemoData();
    renderFusionChain(FUSION_DEMO);
  }

  function getFusionDemoData() {
    return {
      user_id: 'demo', demo: true,
      layers: {
        layer1_variants: [
          { gene_symbol: 'TP53', rsid: 'rs1042522', hgvs: 'NM_000546.5:c.215C>G', clinical_significance: 'Likely Pathogenic', description: '肿瘤抑制基因TP53功能域变异，影响p53蛋白DNA结合能力', allele_frequency: 0.023, source: 'ClinVar' },
          { gene_symbol: 'CYP2C19', rsid: 'rs4244285', hgvs: 'NM_000767.4:c.681G>A', clinical_significance: 'Benign', description: 'CYP2C19*2等位基因，影响氯吡格雷等代谢通道', allele_frequency: 0.286, source: 'PharmGKB' },
          { gene_symbol: 'BRCA1', rsid: 'rs80357713', hgvs: 'NM_007294.3:c.5266dupC', clinical_significance: 'Pathogenic', description: 'BRCA1框移突变，导致同源重组修复功能丧失', allele_frequency: 0.001, source: 'ClinVar' },
          { gene_symbol: 'NRF2', rsid: 'rs6721961', hgvs: 'NM_001313893.2:c.-617C>A', clinical_significance: 'Benign', description: 'NRF2启动子区变异，轻微影响Nrf2/Keap1抗氧化通路活性', allele_frequency: 0.078, source: 'gnomAD' }
        ],
        layer2_proteins: [
          { gene_symbol: 'TP53', uniprot_id: 'P04637', protein_name: 'Cellular tumor antigen p53', function: '转录因子，调控细胞周期 arrest、DNA修复和凋亡', pathways: ['hsa04115','hsa04110'], structure_source: 'AlphaFold', pdb_id: null, interaction_partners: ['MDM2','BAX','CDKN1A'], variant_impact: 'p53蛋白DNA结合域结构不稳定，转录活性下降约60%' },
          { gene_symbol: 'BRCA1', uniprot_id: 'P38398', protein_name: 'Breast cancer type 1 susceptibility protein', function: 'DNA损伤修复（同源重组）、细胞周期检查点调控', pathways: ['hsa03440','hsa03430'], structure_source: 'PDB+AlphaFold', pdb_id: '1JNX', interaction_partners: ['BARD1','RAD51','PALB2'], variant_impact: 'BRCT功能域截短，无法招募RAD51进行同源重组修复' },
          { gene_symbol: 'NRF2', uniprot_id: 'Q16236', protein_name: 'Nuclear factor erythroid 2-related factor 2', function: '抗氧化反应主调节因子，激活Nrf2/Keap1/ARE通路', pathways: ['hsa04140'], structure_source: 'AlphaFold', pdb_id: null, interaction_partners: ['KEAP1','MAFK','ARE'], variant_impact: '启动子活性轻微降低，Nrf2核转位效率下降约15%' }
        ],
        layer3_pathways: [
          { pathway_id: 'hsa03440', name: 'Homologous Recombination', display_name: '同源重组修复通路', description: '高保真DNA双链断裂修复机制，BRCA1/2为核心蛋白', category: 'DNA_repair', status: 'downregulated', score: 35, severity: '严重', related_genes: ['BRCA1','BRCA2','RAD51','PALB2'], tcm_bridge: '肾精不足 → 基因组不稳定 → 肾主生殖发育（先天之本）', method: '基于BRCA1功能丧失(60%↓) + RAD51招募受阻 · 通路活性模型 v2.1' },
          { pathway_id: 'hsa04115', name: 'p53 signaling pathway', display_name: 'p53信号通路', description: 'DNA损伤响应、细胞周期检查点和凋亡调控中枢', category: 'Apoptosis', status: 'downregulated', score: 40, severity: '中度', related_genes: ['TP53','MDM2','CDKN1A','BAX'], tcm_bridge: '气虚证 → 细胞凋亡调控减弱 → 气不摄则脱', method: '基于TP53 p.C215G DNA结合域受损 → 转录活性下降约60% · 蛋白功能-通路映射模型' },
          { pathway_id: 'hsa04140', name: 'Autophagy - animal', display_name: '自噬通路（含AMPK/mTOR）', description: 'AMPK激活自噬、mTOR抑制自噬的双向调控', category: 'AMPK', status: 'normal', score: 68, severity: '正常', related_genes: ['AMPK','mTOR','SIRT1','ULK1'], tcm_bridge: '阴阳平衡 ↔ AMPK/mTOR能量感知双向调控', method: '基于AMPK/mTOR平衡指数 · 参考KEGG通路完整性评估模型' },
          { pathway_id: 'custom_nrf2', name: 'Nrf2/Keap1/ARE pathway', display_name: 'Nrf2抗氧化通路', description: '抗氧化反应元件激活，清除ROS，保护细胞免受氧化损伤', category: 'Nrf2', status: 'slightly_downregulated', score: 58, severity: '轻微', related_genes: ['NRF2','KEAP1','HO-1','NQO1'], tcm_bridge: '阴虚证 → 氧化应激 → Nrf2通路代偿上调不足', method: '基于NRF2启动子活性轻微降低(15%↓) → Nrf2核转位效率 · 启动子-蛋白-通路级联模型' },
          { pathway_id: 'hsa04110', name: 'Cell Cycle', display_name: '细胞周期通路', description: 'G1/S/G2/M检查点调控，p53为核心检查点守门人', category: 'cell_cycle', status: 'slightly_downregulated', score: 55, severity: '轻微', related_genes: ['TP53','CDKN1A','CCND1','RB1'], tcm_bridge: '气滞证 ↔ 细胞增殖失控 ↔ 气机不畅', method: '基于p53信号通路下游检查点蛋白(CDKN1A, CCND1)转录效率 · 级联映射模型' }
        ],
        layer4_syndromes: [
          { name: '气虚证', description: '以气虚乏力、声低懒言、易出汗为主要表现的证候类型', related_pathways: ['hsa04115','hsa04110'], score: 72, confidence: '高', modern_interpretation: '线粒体ATP生成效率降低，AMPK能量感知通路响应减弱', key_evidence: 'p53信号下调 + 细胞周期检查点减弱 → 细胞修复能力整体下降', reference: 'Li S et al., 2021, Phytomedicine · Zhang Z et al., 2023, Cell Prolif.' },
          { name: '肾精不足证', description: '以生长发育迟缓、记忆力减退、腰膝酸软为表现的证候', related_pathways: ['hsa03440'], score: 85, confidence: '高', modern_interpretation: 'DNA修复能力先天性缺陷，基因组稳定性维持能力降低', key_evidence: '同源重组修复通路严重下调（评分35）→ 基因组损伤累积加速', reference: 'Wang X et al., 2022, Front Immunol · Chen Y et al., 2023, J Ethnopharmacol.' },
          { name: '阴虚证', description: '以口干咽燥、五心烦热、潮热盗汗为表现的证候类型', related_pathways: ['custom_nrf2'], score: 58, confidence: '中', modern_interpretation: 'Nrf2抗氧化通路代偿不足，ROS清除能力下降', key_evidence: 'Nrf2启动子变异导致核转位效率降低，抗氧化防御轻度受损', reference: 'Liu J et al., 2020, Oxid Med Cell Longev.' }
        ],
        layer5_interventions: [
          { intervention_type: 'food_medicine', name: '黄芪枸杞代茶饮', description: '黄芪30g、枸杞子15g，沸水冲泡代茶饮。黄芪甲苷通过多靶点网络调控血管保护和免疫功能。', target_pathways: ['hsa04115','custom_nrf2'], target_syndromes: ['气虚证','阴虚证'], active_compounds: ['黄芪甲苷(Astragaloside IV)','枸杞多糖(LBP)','环黄芪醇(CAG)'], cell_repair_mechanism: '黄芪甲苷→PI3K/AKT通路→内皮保护；枸杞多糖→SIRT1去乙酰化→抗衰老', evidence_level: 'validated', usage: '每日1剂，连续饮用，每2周评估调整' },
          { intervention_type: 'food_medicine', name: '人参五味养生粥', description: '人参片6g、五味子5g、山药20g、薏米30g、红枣5枚。人参皂苷Rg1激活AMPK/mTOR通路促进自噬。', target_pathways: ['hsa04140','custom_nrf2','hsa04115'], target_syndromes: ['气虚证','阴虚证'], active_compounds: ['人参皂苷Rg1','人参皂苷Rb1','五味子甲素'], cell_repair_mechanism: '人参皂苷Rg1→AMPK/mTOR→自噬激活；五味子木脂素→Nrf2/Keap1/ARE→抗氧化', evidence_level: 'validated', usage: '每周3-4次，早餐食用' },
          { intervention_type: 'gene_therapy', name: '基因治疗咨询：BRCA1/2同源重组修复', description: '基于BRCA1致病变异的基因治疗选项评估。当前CRISPR-Cas9基因编辑疗法已在镰状细胞病获批。', target_pathways: ['hsa03440'], target_syndromes: ['肾精不足证'], mechanism: 'CRISPR-Cas9介导的精准基因编辑，修复或补偿BRCA1功能', evidence_level: 'preliminary', action: '建议前往正规遗传咨询门诊进行专业评估', contraindications: '目前尚无获批的BRCA基因治疗产品，仅供参考' },
          { intervention_type: 'targeted_drug', name: 'PARP抑制剂敏感性评估', description: 'BRCA1/2功能缺失的肿瘤细胞对PARP抑制剂高度敏感——合成致死策略。', target_pathways: ['hsa03440'], target_syndromes: ['肾精不足证'], mechanism: 'PARP抑制剂阻断单链断裂修复，在BRCA缺陷细胞中引发合成致死', evidence_level: 'validated', action: '如有相关肿瘤风险，由专业顾问评估' },
          { intervention_type: 'pharmacogenomic', name: 'CYP2C19基因代谢指导', description: '您携带CYP2C19*2等位基因（慢代谢型），影响氯吡格雷等代谢。', target_pathways: [], target_syndromes: [], gene_variants: ['CYP2C19'], recommendation: '氯吡格雷：建议换用替格瑞洛（不受CYP2C19影响）', evidence_level: 'validated', source: 'PharmGKB/CPIC' }
        ]
      },
      summary: {
        total_variants: 4, pathogenic_count: 1, benign_count: 2, likely_pathogenic_count: 1,
        pathway_abnormal_count: 3, dominant_syndrome: '气虚证 + 肾精不足证',
        repair_chain_summary: 'BRCA1致病变异→同源重组修复严重缺陷→肾精不足证；TP53变异→p53信号下调→气虚证。核心干预：人参黄芪类药食同源激活AMPK/Nrf2通路进行日常修复；基因治疗和PARP抑制剂作为临床级别选项留存。',
        evidence_note: '本分析基于ClinVar/PharmGKB/gnomAD数据库注释 + TCMSP成分靶点数据。细胞通路评分为模型估算，具体方案请咨询专业顾问。'
      }
    };
  }

  // ==================== 结果信任护栏（消 demo 信任雷） ====================
  // 依据后端返回的 is_demo / analysis_status 显示醒目横幅，并标记结果是否只读。
  function applyResultTrust(data) {
    // 清除上一次的横幅
    var old = document.getElementById('result-trust-banner');
    if (old && old.parentNode) old.parentNode.removeChild(old);

    var isDemo = (!!(data && data.is_demo)) || state.demoMode === true;
    var status = (data && data.analysis_status) || (isDemo ? 'demo' : 'ok');
    var readOnly = isDemo || status === 'unavailable';
    state.resultReadOnly = readOnly;
    state.resultTrust = { isDemo: isDemo, status: status, readOnly: readOnly };

    var banner = document.createElement('div');
    banner.id = 'result-trust-banner';
    banner.style.cssText = 'padding:10px 16px;font-size:0.82rem;font-weight:600;line-height:1.5;text-align:center;margin-bottom:12px;border-radius:10px;';

    if (status === 'unavailable') {
      banner.style.background = 'rgba(239,68,68,0.12)';
      banner.style.color = '#b91c1c';
      banner.style.border = '1px solid rgba(239,68,68,0.4)';
      var reason = (data && data.unavailable_reason) ? ('：' + data.unavailable_reason) : '';
      banner.textContent = '⚠ 真实分析暂不可用，仅展示你本人上传的数据，未生成基因/机制解读' + reason + '。该结果不可保存或分享。';
    } else if (isDemo) {
      banner.style.background = 'rgba(245,158,11,0.12)';
      banner.style.color = '#92400e';
      banner.style.border = '1px solid rgba(245,158,11,0.4)';
      banner.textContent = '⚠ 当前为演示数据，并非你的真实分析结果，请勿用于健康决策，不可保存或分享。';
    } else {
      banner.style.background = 'rgba(16,185,129,0.12)';
      banner.style.color = '#065f46';
      banner.style.border = '1px solid rgba(16,185,129,0.4)';
      banner.textContent = '✓ 基于你的真实健康数据生成 · 可在「我的」中保存与分享';
    }

    // 插入到结果页顶部（优先 page-plan，退而求其次 body 顶部）
    var host = document.getElementById('page-plan') || document.getElementById('page-diagnosis') || document.body;
    if (host === document.body) {
      banner.style.position = 'sticky';
      banner.style.top = '0';
      banner.style.zIndex = '9999';
    }
    if (host.firstChild) {
      host.insertBefore(banner, host.firstChild);
    } else {
      host.appendChild(banner);
    }
  }

  function renderFusionChain(data) {
    if (!data || !data.layers) return;
    applyResultTrust(data);
    var L = data.layers;

    // Layer 1: Gene Variants
    var l1 = document.getElementById('fusion-layer1');
    if (l1 && L.layer1_variants) {
      l1.innerHTML = L.layer1_variants.map(function(v) {
        var tagClass = 'tag-' + v.clinical_significance.toLowerCase().replace(/\s+/g, '-');
        var tagLabel = v.clinical_significance;
        return '<div class="fusion-item">' +
          '<div class="fusion-item-header">' +
            '<span class="fusion-item-name">' + v.gene_symbol + '</span>' +
            '<span class="fusion-item-tag ' + tagClass + '">' + tagLabel + '</span>' +
            (v.rsid ? '<span style="font-size:0.75rem;color:var(--muted);margin-left:auto">' + v.rsid + '</span>' : '') +
          '</div>' +
          '<div class="fusion-item-desc">' + v.description + '</div>' +
          (v.allele_frequency ? '<div class="fusion-item-detail">人群频率: ' + (v.allele_frequency * 100).toFixed(1) + '% · 来源: ' + v.source + '</div>' : '') +
          '</div>';
      }).join('');
    }

    // Layer 2: Proteins
    var l2 = document.getElementById('fusion-layer2');
    if (l2 && L.layer2_proteins) {
      l2.innerHTML = L.layer2_proteins.map(function(p) {
        var partners = (p.interaction_partners || []).join(' · ');
        return '<div class="fusion-item">' +
          '<div class="fusion-item-header">' +
            '<span class="fusion-item-name">' + p.gene_symbol + '</span>' +
            '<span class="fusion-item-tag tag-predicted">' + p.uniprot_id + '</span>' +
          '</div>' +
          '<div class="fusion-item-desc">' + p.protein_name + ' — ' + p.function + '</div>' +
          '<div class="fusion-item-detail">互作蛋白: ' + partners + (p.pdb_id ? ' · PDB: ' + p.pdb_id : '') + '</div>' +
          (p.variant_impact ? '<div class="fusion-tcm-bridge">变异影响: ' + p.variant_impact + '</div>' : '') +
          '</div>';
      }).join('');
    }

    // Layer 3: Pathways (HUB — 三大范式汇合枢纽)
    var l3 = document.getElementById('fusion-layer3');
    if (l3 && L.layer3_pathways) {
      // 汇合枢纽视觉强调
      l3.innerHTML = '<div class="fusion-hub-badge" style="background:linear-gradient(135deg,rgba(16,185,129,0.12),rgba(14,165,233,0.08));border:1px solid rgba(16,185,129,0.15);border-radius:10px;padding:0.65rem 0.85rem;margin-bottom:0.75rem;text-align:center">' +
        '<div style="font-size:0.8rem;font-weight:600;color:var(--accent)">&#x1F9EA; 三大范式汇合枢纽</div>' +
        '<div style="font-size:0.72rem;color:var(--muted);margin-top:0.25rem;line-height:1.5">' +
        '中医细胞修复 · 基因治疗 · 靶向干预 — 三条路径在细胞通路层面殊途同归，' +
        '在这里统一为同一个修复逻辑的五个核心通路' +
        '</div></div>' +
        L.layer3_pathways.map(function(pw) {
        var sevClass = pw.score < 40 ? 'severe' : pw.score < 60 ? 'moderate' : pw.score < 70 ? 'mild' : 'normal';
        var tagClass = 'tag-' + sevClass;
        var barClass = 'bar-' + sevClass;
        var genes = (pw.related_genes || []).join(' · ');
        return '<div class="fusion-item">' +
          '<div class="fusion-item-header">' +
            '<span class="fusion-item-name">' + pw.display_name + '</span>' +
            '<span class="fusion-item-tag ' + tagClass + '">' + pw.severity + '</span>' +
          '</div>' +
          '<div class="fusion-item-desc">' + pw.description + '</div>' +
          '<div class="fusion-pathway-bar ' + barClass + '">' +
            '<span class="fusion-pathway-bar-label">活性</span>' +
            '<div class="fusion-pathway-bar-track"><div class="fusion-pathway-bar-fill" style="width:' + pw.score + '%"></div></div>' +
            '<span class="fusion-pathway-bar-value">' + pw.score + '</span>' +
          '</div>' +
          '<div class="fusion-item-detail">相关基因: ' + genes + '</div>' +
          (pw.tcm_bridge ? '<div class="fusion-tcm-bridge">中医桥接: ' + pw.tcm_bridge + '</div>' : '') +
          (pw.method ? '<div style="font-size:0.7rem;color:var(--muted);margin-top:0.4rem;padding-top:0.4rem;border-top:1px dashed rgba(255,255,255,0.05)">&#128736; 计算: ' + pw.method + '</div>' : '') +
          '</div>';
      }).join('');
    }

    // Layer 4: TCM Syndromes
    var l4 = document.getElementById('fusion-layer4');
    if (l4 && L.layer4_syndromes) {
      // 概念等价性说明
      var conceptEquivalences = {
        '气虚证': '气虚 ↔ 线粒体ATP生成效率降低 · 能量代谢不足',
        '肾精不足证': '肾精不足 ↔ 基因组不稳定性上升 · 先天禀赋不足',
        '阴虚证': '阴虚 ↔ 氧化应激增加 · Nrf2通路代偿不足'
      };
      l4.innerHTML = L.layer4_syndromes.map(function(s) {
        var confClass = s.confidence === '高' ? 'tag-validated' : s.confidence === '中' ? 'tag-predicted' : 'tag-preliminary';
        var conceptEq = conceptEquivalences[s.name] || '';
        return '<div class="fusion-item">' +
          '<div class="fusion-item-header">' +
            '<span class="fusion-item-name">' + s.name + '</span>' +
            '<span class="fusion-item-tag ' + confClass + '">置信度: ' + s.confidence + '</span>' +
          '</div>' +
          '<div class="fusion-item-desc">' + s.description + '</div>' +
          (conceptEq ? '<div style="font-size:0.75rem;color:var(--accent);background:rgba(16,185,129,0.06);padding:0.4rem 0.6rem;border-radius:6px;margin:0.4rem 0 0.5rem;line-height:1.4">&#x2697;&#xFE0F; 概念等价: ' + conceptEq + '</div>' : '') +
          '<div class="fusion-item-detail">现代解读: ' + s.modern_interpretation + '</div>' +
          '<div class="fusion-item-detail">关键证据: ' + s.key_evidence + '</div>' +
          (s.reference ? '<div style="font-size:0.7rem;color:var(--muted);margin-top:0.4rem;padding-top:0.4rem;border-top:1px dashed rgba(255,255,255,0.05)">&#128214; 参考: ' + s.reference + '</div>' : '') +
          '</div>';
      }).join('');
    }

    // Layer 5: Interventions
    var l5 = document.getElementById('fusion-layer5');
    if (l5 && L.layer5_interventions) {
      l5.innerHTML = L.layer5_interventions.map(function(iv) {
        var typeClass = 'badge-' + iv.intervention_type;
        var typeLabel = { food_medicine: '药食同源', gene_therapy: '基因治疗', targeted_drug: '靶向干预', pharmacogenomic: '基因代谢指导' }[iv.intervention_type] || iv.intervention_type;
        var evidenceClass = 'tag-' + iv.evidence_level;
        var evidenceLabel = { validated: '已验证', predicted: '预测中', preliminary: '初步研究' }[iv.evidence_level] || iv.evidence_level;
        return '<div class="fusion-item">' +
          '<div class="fusion-item-header">' +
            '<span class="fusion-item-name">' + iv.name + '</span>' +
          '</div>' +
          '<span class="intervention-type-badge ' + typeClass + '">' + typeLabel + '</span>' +
          '<span class="fusion-item-tag ' + evidenceClass + '">' + evidenceLabel + '</span>' +
          '<div class="fusion-item-desc">' + iv.description + '</div>' +
          (iv.cell_repair_mechanism ? '<div class="fusion-mechanism">修复机制: ' + iv.cell_repair_mechanism + '</div>' : '') +
          (iv.mechanism ? '<div class="fusion-mechanism">机制: ' + iv.mechanism + '</div>' : '') +
          (iv.recommendation ? '<div class="fusion-item-detail">用药建议: ' + iv.recommendation + '</div>' : '') +
          (iv.action ? '<div class="fusion-item-detail">' + iv.action + '</div>' : '') +
          (iv.usage ? '<div class="fusion-usage">' + iv.usage + '</div>' : '') +
          (iv.contraindications ? '<div class="fusion-item-detail" style="color:#f87171">⚠ ' + iv.contraindications + '</div>' : '') +
          '</div>';
      }).join('') +
      // 反馈回路: 干预 → 通路
      '<div class="fusion-connector feedback-loop" style="opacity:0.7">' +
        '<span class="connector-label" style="font-size:0.7rem">反馈回路: 干预执行后重新评估通路活性</span>' +
      '</div>' +
      '<div class="fusion-layer" data-layer="feedback" style="border:1px dashed rgba(16,185,129,0.2);border-radius:10px;padding:0.6rem 0.85rem;text-align:center;background:rgba(16,185,129,0.03)">' +
        '<div style="font-size:0.75rem;color:var(--accent);font-weight:500">&#x21BA; 反馈回路</div>' +
        '<div style="font-size:0.7rem;color:var(--muted);line-height:1.5;margin-top:0.2rem">' +
        '干预执行后，靶向的通路活性将重新评估。<br>人参皂苷Rg1 → AMPK/mTOR通路活性预计提升 15-20% · Nrf2通路活性预计提升 10-15%' +
        '</div>' +
      '</div>';
    }

    // Summary
    var summaryEl = document.getElementById('fusion-summary');
    var summaryText = document.getElementById('fusion-summary-text');
    var evidenceNote = document.getElementById('fusion-evidence-note');
    if (summaryEl && data.summary) {
      summaryEl.style.display = 'block';
      if (summaryText) summaryText.textContent = data.summary.repair_chain_summary;
      if (evidenceNote) evidenceNote.textContent = data.summary.evidence_note;
    }
  }

  // ==================== Unified Plan Page (Fusion Interventions) ====================
  async function loadPlan(forceRefresh) {
    // Demo mode: use built-in demo data
    if (state.demoMode === true) {
      var demoData = getFusionDemoData();
      renderPlanFromFusion(demoData);
      return;
    }

    // Real user mode: try AI diagnosis endpoint for plan data
    try {
      var agentResp = await api('/api/v1/diagnosis/agent-run', {
        method: 'POST',
        body: JSON.stringify({
          genes: state.userGeneVariants || [],
          lab_results: state.userLabResults || [],
          tcm_symptoms: state.userTcmSymptoms || []
        })
      });
      if (agentResp && agentResp.task_id) {
        var chainData = await pollAgentStatus(agentResp.task_id);
        if (chainData) {
          FUSION_DEMO = chainData;
          renderPlanFromFusion(FUSION_DEMO);
          return;
        }
      }
    } catch(e) {
      console.warn('AI plan generation failed, falling back to existing logic', e);
    }

    // Fallback: use cached FUSION_DEMO or built-in demo data
    var data = FUSION_DEMO;
    if (!data) data = getFusionDemoData();
    renderPlanFromFusion(data);
  }

  function renderPlanFromFusion(data) {
    if (!data || !data.layers) return;
    var interventions = data.layers.layer5_interventions || [];
    var container = document.getElementById('plan-interventions');
    if (!container) return;

    var html = '';

    // ---- 核心发现 ----
    if (data.summary) {
      var s = data.summary;
      html += '<div style="background:rgba(16,185,129,0.04);border:1px solid rgba(16,185,129,0.12);border-radius:12px;padding:1rem;margin-bottom:1.25rem">';
      html += '<div style="font-size:0.8rem;font-weight:600;color:var(--accent);margin-bottom:0.4rem;text-transform:uppercase;letter-spacing:0.05em">核心发现</div>';
      html += '<div style="font-size:0.9rem;color:var(--ink);line-height:1.6">' + (s.repair_chain_summary || '') + '</div>';
      if (s.evidence_note) {
        html += '<div style="font-size:0.72rem;color:var(--muted);margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid rgba(16,185,129,0.1)">' + s.evidence_note + '</div>';
      }
      html += '</div>';
    }

    // ---- 药食同源清单（加法思维） ----
    var foodItems = interventions.filter(function(iv) { return iv.intervention_type === 'food_medicine'; });
    if (foodItems.length > 0) {
      html += '<div style="margin-bottom:1.25rem">';
      html += '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.75rem">';
      html += '<span style="font-size:1.1rem">🥗</span>';
      html += '<span style="font-size:0.95rem;font-weight:700;color:var(--ink)">你的专属食养清单</span>';
      html += '</div>';
      html += '<p style="font-size:0.8rem;color:var(--muted);line-height:1.5;margin-bottom:0.75rem">这些不是"必须吃"的规则，而是<strong style="color:var(--accent)">可以试试加入日常饮食</strong>的建议。挑你喜欢的、方便的，什么时候都行。</p>';

      foodItems.forEach(function(iv, idx) {
        var effortLabel = iv.effort || '低';
        var effortColor = effortLabel === '极低' ? '#10b981' : effortLabel === '低' ? '#84cc16' : '#f59e0b';
        html += '<div style="background:#fff;border:1px solid rgba(16,185,129,0.15);border-radius:10px;padding:0.85rem;margin-bottom:0.6rem;position:relative">';
        // 推荐标记
        if (idx === 0) {
          html += '<div style="position:absolute;top:-1px;right:12px;background:var(--accent);color:#fff;font-size:0.65rem;font-weight:600;padding:0.15rem 0.5rem;border-radius:0 0 6px 6px">首推</div>';
        }
        html += '<div style="display:flex;align-items:flex-start;gap:0.5rem">';
        html += '<div style="flex:1">';
        html += '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.3rem">';
        html += '<span style="font-size:0.9rem;font-weight:700;color:var(--ink)">' + iv.name + '</span>';
        html += '<span style="font-size:0.65rem;padding:0.1rem 0.4rem;border-radius:4px;background:' + effortColor + '15;color:' + effortColor + ';font-weight:600">' + effortLabel + '难度</span>';
        html += '</div>';
        html += '<div style="font-size:0.8rem;color:var(--ink);line-height:1.5;margin-bottom:0.4rem">' + iv.description + '</div>';
        // timing
        if (iv.timing) {
          html += '<div style="font-size:0.72rem;color:var(--muted);margin-bottom:0.3rem">⏰ ' + iv.timing + '</div>';
        }
        // usage
        if (iv.usage) {
          html += '<div style="font-size:0.75rem;color:var(--accent);font-weight:500;background:rgba(16,185,129,0.06);padding:0.35rem 0.6rem;border-radius:6px;line-height:1.4">💡 ' + iv.usage + '</div>';
        }
        // mechanism
        if (iv.cell_repair_mechanism) {
          html += '<div style="font-size:0.7rem;color:var(--muted);margin-top:0.35rem;padding-top:0.35rem;border-top:1px dashed rgba(0,0,0,0.05)">' + iv.cell_repair_mechanism + '</div>';
        }
        html += '</div></div>';
        html += '</div>';
      });
      html += '</div>';
    }

    // ---- 基因代谢特点 ----
    var pgxItems = interventions.filter(function(iv) { return iv.intervention_type === 'pharmacogenomic'; });
    if (pgxItems.length > 0) {
      html += '<div style="margin-bottom:1.25rem">';
      html += '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem">';
      html += '<span style="font-size:1.1rem">🧬</span>';
      html += '<span style="font-size:0.9rem;font-weight:600;color:var(--ink)">您的基因代谢特点</span>';
      html += '</div>';
      html += '<p style="font-size:0.75rem;color:var(--muted);margin-bottom:0.6rem">了解身体对成分的反应方式，帮助您和顾问做出更精准的成分选择</p>';
      pgxItems.forEach(function(iv) {
        html += '<div style="background:#fff;border:1px solid rgba(14,165,233,0.15);border-radius:8px;padding:0.7rem 0.85rem;margin-bottom:0.5rem">';
        html += '<div style="font-size:0.85rem;font-weight:600;color:var(--ink);margin-bottom:0.3rem">' + iv.name + '</div>';
        html += '<div style="font-size:0.78rem;color:var(--ink);line-height:1.5">' + iv.description + '</div>';
        if (iv.recommendation) html += '<div style="font-size:0.75rem;color:var(--accent);margin-top:0.3rem">' + iv.recommendation + '</div>';
        html += '</div>';
      });
      html += '</div>';
    }

    // ---- 临床级选项（仅当存在时显示） ----
    var clinicalItems = interventions.filter(function(iv) { return iv.intervention_type === 'gene_therapy' || iv.intervention_type === 'targeted_drug'; });
    if (clinicalItems.length > 0) {
      html += '<div style="margin-bottom:1rem">';
      html += '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem">';
      html += '<span style="font-size:1.1rem">🏥</span>';
      html += '<span style="font-size:0.9rem;font-weight:600;color:var(--ink)">临床级参考信息</span>';
      html += '</div>';
      html += '<div style="padding:0.6rem 0.75rem;background:rgba(248,113,113,0.06);border-left:3px solid #f87171;border-radius:0 8px 8px 0;font-size:0.72rem;color:#f87171;line-height:1.5;margin-bottom:0.6rem">';
      html += '<strong>提示</strong>：以下为临床级参考信息，由专业顾问评估后方可实施。本平台不提供医疗建议。';
      html += '</div>';
      clinicalItems.forEach(function(iv) {
        html += '<div style="background:#fff;border:1px solid rgba(248,113,113,0.12);border-radius:8px;padding:0.7rem 0.85rem;margin-bottom:0.5rem">';
        html += '<div style="font-size:0.85rem;font-weight:600;color:var(--ink);margin-bottom:0.3rem">' + iv.name + '</div>';
        html += '<div style="font-size:0.78rem;color:var(--ink);line-height:1.5">' + iv.description + '</div>';
        if (iv.mechanism) html += '<div style="font-size:0.72rem;color:var(--muted);margin-top:0.3rem">' + iv.mechanism + '</div>';
        if (iv.action) html += '<div style="font-size:0.75rem;color:#f87171;margin-top:0.3rem">' + iv.action + '</div>';
        html += '</div>';
      });
      html += '</div>';
    }

    container.innerHTML = html;

    // ---- 日常修复 ----
    var dailySection = document.getElementById('plan-daily-section');
    if (dailySection) {
      dailySection.style.display = 'block';
      var dailyPillars = document.getElementById('plan-daily-pillars');
      if (dailyPillars && DEMO.repair && DEMO.repair.dailyPillars) {
        dailyPillars.innerHTML = DEMO.repair.dailyPillars.map(function(p, i) {
          return '<div class="pillar-card' + (i === 0 ? ' active' : '') + '" data-index="' + i + '">' +
            '<span class="pillar-icon">' + p.icon + '</span>' +
            '<span class="pillar-name">' + p.name + '</span>' +
            '<span class="pillar-score">' + p.score + '分</span>' +
            '</div>';
        }).join('');
        dailyPillars.querySelectorAll('.pillar-card').forEach(function(card) {
          card.addEventListener('click', function() {
            dailyPillars.querySelectorAll('.pillar-card').forEach(function(c) { c.classList.remove('active'); });
            this.classList.add('active');
          });
        });
      }
    }

    // CTA
    var hasClinical = clinicalItems.length > 0;
    var ctaSection = document.getElementById('plan-cta-section');
    if (ctaSection) {
      ctaSection.style.display = hasClinical ? 'block' : 'none';
    }
  }

  // ==================== Timer Functions ====================
  function initTimers() {
    // Baduanjin timer (count up)
    var bjDisplay = document.querySelector('#baduanjin-timer .timer-display');
    var bjStart = document.querySelector('#baduanjin-timer .timer-start');
    var bjPause = document.querySelector('#baduanjin-timer .timer-pause');
    var bjReset = document.querySelector('#baduanjin-timer .timer-reset');
    if (bjDisplay && bjStart) {
      var bjSeconds = 0;
      bjStart.addEventListener('click', function() {
        if (sleepTimers.baduanjin) return;
        sleepTimers.baduanjin = setInterval(function() {
          bjSeconds++;
          var m = String(Math.floor(bjSeconds / 60)).padStart(2, '0');
          var s = String(bjSeconds % 60).padStart(2, '0');
          bjDisplay.textContent = m + ':' + s;
        }, 1000);
        showToast('八段锦练习开始计时', 'info');
      });
      if (bjPause) bjPause.addEventListener('click', function() {
        if (sleepTimers.baduanjin) { clearInterval(sleepTimers.baduanjin); sleepTimers.baduanjin = null; showToast('计时已暂停', 'info'); }
      });
      if (bjReset) bjReset.addEventListener('click', function() {
        if (sleepTimers.baduanjin) { clearInterval(sleepTimers.baduanjin); sleepTimers.baduanjin = null; }
        bjSeconds = 0; bjDisplay.textContent = '00:00';
      });
    }

    // Moxa timer (count down from 15:00 = 900s)
    var mxDisplay = document.querySelector('#moxa-timer .timer-display');
    var mxStart = document.querySelector('#moxa-timer .timer-start');
    var mxPause = document.querySelector('#moxa-timer .timer-pause');
    var mxReset = document.querySelector('#moxa-timer .timer-reset');
    if (mxDisplay && mxStart) {
      var mxRemaining = 900;
      mxDisplay.textContent = '15:00';
      mxStart.addEventListener('click', function() {
        if (sleepTimers.moxa) return;
        if (mxRemaining <= 0) mxRemaining = 900;
        sleepTimers.moxa = setInterval(function() {
          mxRemaining--;
          var m = String(Math.floor(mxRemaining / 60)).padStart(2, '0');
          var s = String(mxRemaining % 60).padStart(2, '0');
          mxDisplay.textContent = m + ':' + s;
          if (mxRemaining <= 0) {
            clearInterval(sleepTimers.moxa); sleepTimers.moxa = null;
            showToast('艾灸时间到！请注意安全', 'success');
          }
        }, 1000);
        showToast('艾灸计时开始', 'info');
      });
      if (mxPause) mxPause.addEventListener('click', function() {
        if (sleepTimers.moxa) { clearInterval(sleepTimers.moxa); sleepTimers.moxa = null; showToast('计时已暂停', 'info'); }
      });
      if (mxReset) mxReset.addEventListener('click', function() {
        if (sleepTimers.moxa) { clearInterval(sleepTimers.moxa); sleepTimers.moxa = null; }
        mxRemaining = 900; mxDisplay.textContent = '15:00';
      });
    }
  }

  // ==================== Button Response Helpers ====================
  function initButtonResponses() {
    // Report view buttons
    document.querySelectorAll('.report-file-card .btn').forEach(function(btn) {
      if (btn.textContent.trim() === '\u67E5\u770B') {
        btn.addEventListener('click', function(e) {
          e.preventDefault();
          showToast('报告详情功能即将上线，敬请期待', 'info');
        });
      }
      if (btn.textContent.trim() === '\u5220\u9664') {
        btn.addEventListener('click', function(e) {
          e.preventDefault();
          var card = this.closest('.report-file-card');
          card.style.opacity = '0.3';
          card.style.transform = 'scale(0.95)';
          setTimeout(function() { card.style.display = 'none'; }, 300);
          showToast('报告已移除', 'success');
        });
      }
    });

    // Doctor review buttons
    document.querySelectorAll('.review-actions .btn-primary').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        showToast('分析审核功能即将上线', 'info');
      });
    });
    document.querySelectorAll('.review-actions .btn-ghost').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        showToast('用户详情功能即将上线', 'info');
      });
    });

    // Prescription form submit
    var rxForm = document.querySelector('.prescription-form');
    if (rxForm) {
      rxForm.addEventListener('submit', function(e) {
        e.preventDefault();
        showToast('方案提交功能即将上线', 'info');
      });
    }

    // Report actions (records page)
    document.querySelectorAll('.report-actions .btn').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        showToast(this.textContent + ' 功能即将上线', 'info');
      });
    });

    // Nonpharma guide buttons
    document.querySelectorAll('.nonpharma-card .btn-outline').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        showToast('定位指导功能即将上线，敬请期待', 'info');
      });
    });

    // Play soothing music button (if exists)
    var playMusicBtn = document.querySelector('.nonpharma-card .btn-info, .nonpharma-card button:last-of-type');
    if (playMusicBtn && playMusicBtn.textContent.includes('\u64AD\u653E')) {
      playMusicBtn.addEventListener('click', function(e) {
        e.preventDefault();
        showToast('音乐播放功能即将上线', 'info');
      });
    }

    // Score detail link
    var scoreDetailLink = document.getElementById('show-score-detail');
    if (scoreDetailLink) {
      scoreDetailLink.addEventListener('click', function(e) {
        e.preventDefault();
        // Navigate to repair page which has full breakdown
        document.querySelectorAll('.nav-item[data-page="repair"]').forEach(function(nav) { nav.click(); });
      });
    }

    // Todo checkbox save state
    document.querySelectorAll('.todo-check').forEach(function(cb) {
      cb.addEventListener('change', function() {
        var textEl = this.nextElementSibling;
        if (textEl) textEl.classList.toggle('done', this.checked);
        var done = document.querySelectorAll('.todo-check:checked').length;
        var total = document.querySelectorAll('.todo-check').length;
        if (done === total) {
          showToast('今日健康待办全部完成！', 'success');
        }
      });
    });

    // Notification bell
    var notifBell = document.querySelector('.notification-bell');
    if (notifBell) {
      notifBell.addEventListener('click', function() {
        showToast('消息中心即将上线', 'info');
      });
    }

    // Sidebar profile/messages
    document.querySelectorAll('.sidebar-link').forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        showToast(this.textContent.trim() + ' 功能即将上线', 'info');
      });
    });

    // Global search
    var searchInput = document.getElementById('global-search');
    if (searchInput) {
      searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var query = this.value.trim();
          if (query) {
            var pages = ['today','dashboard','diagnosis','plan','trends','reports','growth','knowledge'];
            var match = pages.find(function(p) {
              var titles = {today:'今日',dashboard:'健康全景',diagnosis:'融合分析',plan:'修复方案',trends:'趋势',reports:'检测报告',growth:'成长中心',knowledge:'健康知识'};
              return titles[p].indexOf(query) !== -1;
            });
            if (match) {
              document.querySelectorAll('.nav-item[data-page="' + match + '"]').forEach(function(nav) { nav.click(); });
              this.value = '';
            } else {
              showToast('未找到"' + query + '"相关功能', 'info');
            }
          }
        }
      });
    }
  }

  // ==================== Consultant Workstation ====================
  async function loadConsultant(forceRefresh) {
    if (state.demoMode) {
      renderConsultantStats(DEMO.consultantStats);
      renderConsultantReviews(DEMO.consultantReviews);
      setupConsultantInteractions(DEMO.consultantStats);
      return;
    }

    if (state.cache.consultant && !forceRefresh) {
      renderConsultantStats(state.cache.consultant.stats);
      renderConsultantReviews(state.cache.consultant.reviews);
      setupConsultantInteractions(state.cache.consultant.stats);
      return;
    }

    // Load pending reviews and stats in parallel
    var reviewsPromise = api('/api/v1/diagnosis/results?status=pending');
    var statsPromise = api('/api/v1/dashboard/overview', { silent: true });

    var reviewsData = await reviewsPromise;
    var statsData = await statsPromise;

    var reviews = (reviewsData && reviewsData.results) ? reviewsData.results : (reviewsData || DEMO.consultantReviews);
    var stats = (statsData && statsData.consultant_stats) ? statsData.consultant_stats : DEMO.consultantStats;

    state.cache.consultant = { reviews: reviews, stats: stats };
    renderConsultantStats(stats);
    renderConsultantReviews(reviews);
    setupConsultantInteractions(stats);
  }

  function setupConsultantInteractions(stats) {
    // 1. \u7528\u6237\u5361\u7247\u70B9\u51FB\u4E8B\u4EF6
    var reviewItems = document.querySelectorAll('.review-item');
    reviewItems.forEach(function (item) {
      item.style.cursor = 'pointer';
      item.style.transition = 'transform 0.2s ease, box-shadow 0.2s ease';
      item.addEventListener('mouseenter', function () {
        item.style.transform = 'translateY(-2px)';
        item.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)';
      });
      item.addEventListener('mouseleave', function () {
        item.style.transform = '';
        item.style.boxShadow = '';
      });
      item.addEventListener('click', function (e) {
        if (e.target.closest('.btn-confirm') || e.target.closest('.btn-reject')) return;
        showToast('\u7528\u6237\u8BE6\u60C5\u529F\u80FD\u5F00\u53D1\u4E2D', 'info');
      });
    });

    // 2. \u5BA1\u6838\u6309\u94AE\u52A8\u753B\u6548\u679C\u589E\u5F3A
    var confirmBtns = document.querySelectorAll('.review-item .btn-confirm');
    confirmBtns.forEach(function (btn) {
      var originalClickHandlers = btn.onclick;
      btn.addEventListener('click', function () {
        btn.style.transform = 'scale(0.92)';
        setTimeout(function () { btn.style.transform = ''; }, 150);
      });
    });
    var rejectBtns = document.querySelectorAll('.review-item .btn-reject');
    rejectBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        btn.style.transform = 'scale(0.92)';
        setTimeout(function () { btn.style.transform = ''; }, 150);
      });
    });

    // 3. \u201C\u4ECA\u65E5\u5F85\u5904\u7406\u201D\u8BA1\u6570 badge
    var pendingCount = (stats && stats.pending) || 0;
    var firstStatCard = document.querySelector('.stat-card');
    if (firstStatCard && pendingCount > 0) {
      var existingBadge = firstStatCard.querySelector('.today-pending-badge');
      if (!existingBadge) {
        var badge = document.createElement('span');
        badge.className = 'today-pending-badge';
        badge.textContent = pendingCount + ' \u4EF6\u5F85\u5904\u7406';
        badge.style.cssText = 'display:inline-block;background:linear-gradient(90deg,#ff6b00,#ff4500);color:#fff;font-size:11px;font-weight:600;padding:2px 10px;border-radius:20px;margin-top:8px;animation:badge-pulse 2s ease-in-out infinite;';
        // Add keyframes if not already present
        if (!document.getElementById('consultant-badge-style')) {
          var badgeStyle = document.createElement('style');
          badgeStyle.id = 'consultant-badge-style';
          badgeStyle.textContent = '@keyframes badge-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.85;transform:scale(1.03)}}';
          document.head.appendChild(badgeStyle);
        }
        firstStatCard.appendChild(badge);
      }
    }
  }

  function renderConsultantStats(stats) {
    if (!stats) return;
    var statCards = document.querySelectorAll('.stat-card .stat-number');
    var keys = ['pending', 'today_plans', 'my_users', 'accuracy'];
    statCards.forEach(function (el, i) {
      if (keys[i] && stats[keys[i]] !== undefined) {
        el.textContent = stats[keys[i]];
      }
    });
  }

  function renderConsultantReviews(reviews) {
    var container = document.querySelector('.review-list');
    if (!container) return;
    if (!reviews || reviews.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">\u6682\u65E0\u5F85\u5BA1\u6838\u5206\u6790</div></div>';
      return;
    }
    var html = '';
    reviews.forEach(function (r) {
      var userName = r.user_name || '\u672A\u77E5\u7528\u6237';
      var avatar = r.user_avatar || userName.charAt(0);
      var gender = r.gender || '\u7537';
      var age = r.age || '';
      var date = r.created_at || r.date || '';
      var analysis = r.ai_analysis || r.analysis || r.summary || '\u672A\u77E5\u5206\u6790';
      var confidence = r.confidence || r.ai_confidence || 0;

      html +=
        '<div class="review-item" data-review-id="' + r.id + '">' +
        '  <div class="review-user">' +
        '    <div class="user-avatar">' + escapeHtml(avatar) + '</div>' +
        '    <div class="user-info">' +
        '      <span class="user-name">' + escapeHtml(userName) + '</span>' +
        '      <span class="user-meta">' + escapeHtml(gender) + ' \u00B7 ' + escapeHtml(age + '\u5C81') + ' \u00B7 ' + escapeHtml(date) + '</span>' +
        '    </div>' +
        '  </div>' +
        '  <div class="review-analysis">' +
        '    <span class="ai-analysis">AI\u5206\u6790: ' + escapeHtml(analysis) + '</span>' +
        '    <span class="ai-confidence">\u7F6E\u4FE1\u5EA6: ' + confidence + '%</span>' +
        '  </div>' +
        '  <div class="review-actions">' +
        '    <button class="btn btn-sm btn-primary btn-confirm">\u786E\u8BA4</button>' +
        '    <button class="btn btn-sm btn-ghost btn-reject">\u9A73\u56DE</button>' +
        '  </div>' +
        '</div>';
    });
    container.innerHTML = html;

    // Bind confirm/reject buttons
    container.querySelectorAll('.btn-confirm').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var item = btn.closest('.review-item');
        var reviewId = item.dataset.reviewId;
        btn.classList.add('loading');
        var result = await api('/api/v1/diagnosis/results/' + reviewId, {
          method: 'PUT',
          body: JSON.stringify({ status: 'confirmed' })
        });
        btn.classList.remove('loading');
        if (result) {
          showSuccessToast('\u8BCA\u65AD\u5DF2\u786E\u8BA4');
          item.style.opacity = '0.5';
          item.style.pointerEvents = 'none';
          // Update pending count
          var pendingEl = document.querySelector('.stat-card .stat-number');
          if (pendingEl) {
            var current = parseInt(pendingEl.textContent) || 0;
            pendingEl.textContent = Math.max(0, current - 1);
          }
        }
      });
    });

    container.querySelectorAll('.btn-reject').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var item = btn.closest('.review-item');
        var reviewId = item.dataset.reviewId;
        btn.classList.add('loading');
        var result = await api('/api/v1/diagnosis/results/' + reviewId, {
          method: 'PUT',
          body: JSON.stringify({ status: 'rejected' })
        });
        btn.classList.remove('loading');
        if (result) {
          showSuccessToast('\u8BCA\u65AD\u5DF2\u9A73\u56DE');
          item.style.opacity = '0.5';
          item.style.pointerEvents = 'none';
          var pendingEl = document.querySelector('.stat-card .stat-number');
          if (pendingEl) {
            var current = parseInt(pendingEl.textContent) || 0;
            pendingEl.textContent = Math.max(0, current - 1);
          }
        }
      });
    });
  }

  // ==================== Trend Chart ====================
  var trendMetricConfigs = {
    glucose: { label: '\u7A7A\u8179\u8840\u7CD6 (mmol/L)', color: '#ff9500', reference: 6.1, unit: 'mmol/L' },
    pressure: { label: '\u6536\u7F29\u538B (mmHg)', color: '#007aff', reference: 140, unit: 'mmHg' },
    weight: { label: '\u4F53\u91CD (kg)', color: '#0d8a6a', reference: null, unit: 'kg' }
  };

  async function initTrendChart() {
    var container = document.getElementById('trend-chart');
    if (!container) return;

    var metric = state.trendMetric;
    var config = trendMetricConfigs[metric];
    if (!config) return;

    // Use cached demo data initially
    if (state.demoMode) {
      drawLineChart(container, DEMO.trend[metric]);
      return;
    }

    // Build date range: last 30 days
    var toDate = new Date();
    var fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - 30);
    var fromStr = fromDate.toISOString().split('T')[0];
    var toStr = toDate.toISOString().split('T')[0];
    var loincCode = LOINC_CODES[metric];

    try {
      var data = await api('/api/v1/observations/trend?code=' + loincCode + '&from_date=' + fromStr + '&to_date=' + toStr, { silent: true });
      if (data && data.observations && data.observations.length > 0) {
        var chartData = {
          label: config.label,
          values: data.observations.map(function (o) { return o.value; }),
          dates: data.observations.map(function (o) { return formatDate(o.date); }),
          color: config.color,
          reference: data.reference_high || config.reference
        };
        drawLineChart(container, chartData);
      } else {
        // Fallback to demo data
        drawLineChart(container, DEMO.trend[metric]);
      }
    } catch (err) {
      drawLineChart(container, DEMO.trend[metric]);
    }
  }

  function drawLineChart(container, data) {
    if (!data || !data.values || data.values.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">\u6682\u65E0\u8D8B\u52BF\u6570\u636E</div></div>';
      return;
    }
    var width = container.clientWidth || 600;
    var height = 280;
    var padding = { top: 30, right: 30, bottom: 40, left: 50 };
    var chartW = width - padding.left - padding.right;
    var chartH = height - padding.top - padding.bottom;

    var minVal = Math.min.apply(null, data.values) * 0.95;
    var maxVal = Math.max.apply(null, data.values) * 1.05;
    if (data.reference) {
      minVal = Math.min(minVal, data.reference * 0.95);
      maxVal = Math.max(maxVal, data.reference * 1.05);
    }
    if (minVal === maxVal) {
      minVal -= 1;
      maxVal += 1;
    }

    var svg = '<svg width="' + width + '" height="' + height + '" style="overflow:visible">';

    // Grid lines
    for (var i = 0; i <= 4; i++) {
      var y = padding.top + (chartH / 4) * i;
      var val = maxVal - (maxVal - minVal) / 4 * i;
      svg += '<line x1="' + padding.left + '" y1="' + y + '" x2="' + (width - padding.right) + '" y2="' + y + '" stroke="#e5e7eb" stroke-width="1"/>';
      svg += '<text x="' + (padding.left - 10) + '" y="' + (y + 4) + '" text-anchor="end" font-size="11" fill="#6b7280">' + val.toFixed(1) + '</text>';
    }

    // Reference line
    if (data.reference) {
      var refY = padding.top + chartH - ((data.reference - minVal) / (maxVal - minVal)) * chartH;
      svg += '<line x1="' + padding.left + '" y1="' + refY + '" x2="' + (width - padding.right) + '" y2="' + refY + '" stroke="#ff3b30" stroke-width="1" stroke-dasharray="4,4" opacity="0.6"/>';
      svg += '<text x="' + (width - padding.right + 5) + '" y="' + (refY + 4) + '" font-size="10" fill="#ff3b30">\u53C2\u8003\u503C</text>';
    }

    // Data line
    var points = data.values.map(function (v, i) {
      var x = data.values.length === 1 ? padding.left + chartW / 2 : padding.left + (chartW / (data.values.length - 1)) * i;
      var py = padding.top + chartH - ((v - minVal) / (maxVal - minVal)) * chartH;
      return x + ',' + py;
    }).join(' ');

    svg += '<polyline points="' + points + '" fill="none" stroke="' + data.color + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';

    // Area fill
    if (data.values.length > 1) {
      var lastX = padding.left + chartW;
      var areaPoints = points + ' ' + lastX + ',' + (padding.top + chartH) + ' ' + padding.left + ',' + (padding.top + chartH);
      svg += '<polygon points="' + areaPoints + '" fill="' + data.color + '" opacity="0.08"/>';
    }

    // Data points
    data.values.forEach(function (v, i) {
      var x = data.values.length === 1 ? padding.left + chartW / 2 : padding.left + (chartW / (data.values.length - 1)) * i;
      var py = padding.top + chartH - ((v - minVal) / (maxVal - minVal)) * chartH;
      svg += '<circle cx="' + x + '" cy="' + py + '" r="5" fill="' + data.color + '" stroke="white" stroke-width="2"/>';
      svg += '<text x="' + x + '" y="' + (py - 10) + '" text-anchor="middle" font-size="11" font-weight="600" fill="' + data.color + '">' + v + '</text>';
    });

    // X-axis labels (show at most ~8 labels to avoid overlap)
    var dates = data.dates;
    var step = Math.max(1, Math.ceil(dates.length / 8));
    dates.forEach(function (d, i) {
      if (i % step !== 0 && i !== dates.length - 1) return;
      var x = dates.length === 1 ? padding.left + chartW / 2 : padding.left + (chartW / (dates.length - 1)) * i;
      svg += '<text x="' + x + '" y="' + (height - 10) + '" text-anchor="middle" font-size="11" fill="#6b7280">' + d + '</text>';
    });

    svg += '</svg>';
    container.innerHTML = svg;
  }

  // Trend tab switching
  trendTabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      trendTabs.forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      state.trendMetric = tab.dataset.metric;
      initTrendChart();
    });
  });

  // ==================== Constitution Mini Chart (Dashboard) ====================
  async function initConstitutionMiniChart() {
    var container = document.getElementById('constitution-mini-chart');
    if (!container) return;

    var scores = null;

    // Try to get scores from cache or API
    if (state.constitutionScores) {
      scores = state.constitutionScores;
    } else if (!state.demoMode) {
      var data = await api('/api/v1/tcm/constitution', { silent: true });
      if (data && data.constitution_scores) {
        scores = data.constitution_scores;
        state.constitutionScores = scores;
        state.constitutionType = data.constitution_type;
      }
    }

    var labels = ['\u5E73\u548C', '\u6C14\u865A', '\u9633\u865A', '\u9634\u865A', '\u75F0\u6E7F', '\u6E7F\u70ED', '\u8840\u7600', '\u6C14\u90C1', '\u7279\u79C0'];
    var values;
    if (scores) {
      values = labels.map(function (l) {
        var key = l + '\u8D28';
        return (scores[key] !== undefined) ? scores[key] : 20;
      });
    } else {
      values = [55, 72, 45, 30, 38, 25, 20, 35, 15];
    }

    drawRadarChart(container, labels, values, 200);
  }

  // ==================== Constitution Radar Chart (TCM Page) ====================
  async function initConstitutionRadarChart() {
    var container = document.getElementById('constitution-radar-chart');
    if (!container) return;

    var scores = null;

    if (state.constitutionScores) {
      scores = state.constitutionScores;
    } else if (!state.demoMode && state.cache.tcm && state.cache.tcm.constitution_scores) {
      scores = state.cache.tcm.constitution_scores;
    } else if (!state.demoMode) {
      var data = await api('/api/v1/tcm/constitution', { silent: true });
      if (data && data.constitution_scores) {
        scores = data.constitution_scores;
        state.constitutionScores = scores;
        state.constitutionType = data.constitution_type;
      }
    }

    var labels = ['\u5E73\u548C\u8D28', '\u6C14\u865A\u8D28', '\u9633\u865A\u8D28', '\u9634\u865A\u8D28', '\u75F0\u6E7F\u8D28', '\u6E7F\u70ED\u8D28', '\u8840\u7600\u8D28', '\u6C14\u90C1\u8D28', '\u7279\u79C0\u8D28'];
    var values;
    if (scores) {
      values = labels.map(function (l) {
        return (scores[l] !== undefined) ? scores[l] : 20;
      });
    } else {
      values = [55, 72, 45, 30, 38, 25, 20, 35, 15];
    }

    drawRadarChart(container, labels, values, 400);
  }

  function drawRadarChart(container, labels, values, size) {
    if (!container || !labels || !values) return;
    var width = container.clientWidth || size;
    var height = size;
    var centerX = width / 2;
    var centerY = height / 2;
    var radius = Math.min(width, height) / 2 - 40;
    var n = labels.length;

    var svg = '<svg width="' + width + '" height="' + height + '">';

    // Grid polygons
    for (var level = 1; level <= 5; level++) {
      var r = (radius / 5) * level;
      var points = '';
      for (var i = 0; i < n; i++) {
        var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
        var x = centerX + r * Math.cos(angle);
        var y = centerY + r * Math.sin(angle);
        points += x + ',' + y + ' ';
      }
      svg += '<polygon points="' + points.trim() + '" fill="none" stroke="#e5e7eb" stroke-width="1"/>';
    }

    // Axis lines
    for (var i = 0; i < n; i++) {
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var x = centerX + radius * Math.cos(angle);
      var y = centerY + radius * Math.sin(angle);
      svg += '<line x1="' + centerX + '" y1="' + centerY + '" x2="' + x + '" y2="' + y + '" stroke="#e5e7eb" stroke-width="1"/>';
    }

    // Data polygon
    var dataPoints = '';
    for (var i = 0; i < n; i++) {
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var r = (values[i] / 100) * radius;
      var x = centerX + r * Math.cos(angle);
      var y = centerY + r * Math.sin(angle);
      dataPoints += x + ',' + y + ' ';
    }
    svg += '<polygon points="' + dataPoints.trim() + '" fill="rgba(13,138,106,0.15)" stroke="#0d8a6a" stroke-width="2"/>';

    // Data points
    for (var i = 0; i < n; i++) {
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var r = (values[i] / 100) * radius;
      var x = centerX + r * Math.cos(angle);
      var y = centerY + r * Math.sin(angle);
      svg += '<circle cx="' + x + '" cy="' + y + '" r="4" fill="#0d8a6a" stroke="white" stroke-width="2"/>';
    }

    // Labels
    for (var i = 0; i < n; i++) {
      var angle = (Math.PI * 2 / n) * i - Math.PI / 2;
      var r = radius + 22;
      var x = centerX + r * Math.cos(angle);
      var y = centerY + r * Math.sin(angle);
      var anchor = x > centerX + 10 ? 'start' : x < centerX - 10 ? 'end' : 'middle';
      var baseline = y > centerY + 10 ? 'hanging' : y < centerY - 10 ? 'auto' : 'middle';
      svg += '<text x="' + x + '" y="' + y + '" text-anchor="' + anchor + '" dominant-baseline="' + baseline + '" font-size="12" fill="#6b7280" font-weight="500">' + labels[i] + '</text>';
    }

    svg += '</svg>';
    container.innerHTML = svg;
  }

  // ==================== Modal ====================
  uploadBtn.addEventListener('click', function () {
    uploadModal.classList.remove('hidden');
  });

  // Upload modal close
  var uploadModalClose = uploadModal.querySelector('.modal-close');
  var uploadModalOverlay = uploadModal.querySelector('.modal-overlay');
  if (uploadModalClose) uploadModalClose.addEventListener('click', function () {
    uploadModal.classList.add('hidden');
    resetUploadUI();
  });
  if (uploadModalOverlay) uploadModalOverlay.addEventListener('click', function () {
    uploadModal.classList.add('hidden');
    resetUploadUI();
  });

  // Records page upload button
  var recordsUploadBtn = document.querySelector('.records-sidebar .btn-secondary.btn-block');
  if (recordsUploadBtn) {
    recordsUploadBtn.addEventListener('click', function () {
      uploadModal.classList.remove('hidden');
    });
  }

  function resetUploadUI() {
    var progressArea = document.querySelector('.upload-progress');
    var progressFill = document.querySelector('.progress-fill');
    var progressText = document.querySelector('.progress-text');
    if (progressArea) progressArea.classList.add('hidden');
    if (progressFill) progressFill.style.width = '0%';
    if (progressText) progressText.textContent = '\u6B63\u5728\u4E0A\u4F20...';
    if (fileInput) fileInput.value = '';
  }

  // ==================== File Upload ====================
  dropzone.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', handleFileUpload);

  function handleFileUpload(e) {
    var file = e.target.files[0];
    if (!file) return;
    doUploadFile(file);
  }

  function doUploadFile(file) {
    var progressArea = document.querySelector('.upload-progress');
    var progressFill = document.querySelector('.progress-fill');
    var progressText = document.querySelector('.progress-text');

    if (!progressArea || !progressFill || !progressText) return;

    progressArea.classList.remove('hidden');
    progressFill.style.width = '0%';
    progressText.textContent = '\u6B63\u5728\u4E0A\u4F20... 0%';

    // Validate file size (20MB max)
    if (file.size > 20 * 1024 * 1024) {
      showErrorToast('\u6587\u4EF6\u5927\u5C0F\u8D85\u8FC720MB\u9650\u5236');
      progressArea.classList.add('hidden');
      return;
    }

    if (state.demoMode) {
      // Simulate upload in demo mode
      var progress = 0;
      var interval = setInterval(function () {
        progress += Math.random() * 20;
        if (progress >= 100) {
          progress = 100;
          clearInterval(interval);
          progressFill.style.width = '100%';
          progressText.textContent = '\u4E0A\u4F20\u5B8C\u6210\uFF01\u6B63\u5728\u89E3\u6790...';
          setTimeout(function () {
            uploadModal.classList.add('hidden');
            resetUploadUI();
            showSuccessToast('\u62A5\u544A\u4E0A\u4F20\u6210\u529F\uFF01(\u6F14\u793A\u6A21\u5F0F)');
            // Refresh records
            state.cache.records = null;
            if (state.currentPage === 'records') loadRecords(true);
          }, 1500);
        }
        progressFill.style.width = Math.min(progress, 100) + '%';
        progressText.textContent = '\u6B63\u5728\u4E0A\u4F20... ' + Math.round(Math.min(progress, 100)) + '%';
      }, 300);
      return;
    }

    // Real API upload with XHR progress
    apiUpload('/api/v1/records/upload', file, function (percent) {
      progressFill.style.width = percent + '%';
      progressText.textContent = '\u6B63\u5728\u4E0A\u4F20... ' + percent + '%';
    }).then(function (result) {
      progressFill.style.width = '100%';
      progressText.textContent = '\u4E0A\u4F20\u5B8C\u6210\uFF01\u6B63\u5728\u89E3\u6790...';
      showSuccessToast('\u62A5\u544A\u4E0A\u4F20\u6210\u529F\uFF0CAI\u6B63\u5728\u5206\u6790\u4E2D');
      setTimeout(function () {
        uploadModal.classList.add('hidden');
        resetUploadUI();
        // Refresh records list
        state.cache.records = null;
        if (state.currentPage === 'records') loadRecords(true);
      }, 1500);
    }).catch(function (err) {
      progressArea.classList.add('hidden');
      showErrorToast('\u4E0A\u4F20\u5931\u8D25: ' + (err.message || '\u672A\u77E5\u9519\u8BEF'));
      resetUploadUI();
    });
  }

  // Drag and drop support
  if (dropzone) {
    dropzone.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = '#0d8a6a';
      dropzone.style.background = 'rgba(13,138,106,0.05)';
    });
    dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = '';
      dropzone.style.background = '';
    });
    dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = '';
      dropzone.style.background = '';
      var files = e.dataTransfer.files;
      if (files.length > 0) {
        doUploadFile(files[0]);
      }
    });
  }

  // ==================== Todo Checkboxes ====================
  function rebindTodoCheckboxes() {
    document.querySelectorAll('.todo-check').forEach(function (checkbox) {
      // Remove existing listeners by replacing node
      var newCheck = checkbox.cloneNode(true);
      checkbox.parentNode.replaceChild(newCheck, checkbox);
      newCheck.addEventListener('change', function () {
        var text = newCheck.nextElementSibling;
        if (text) text.classList.toggle('done', newCheck.checked);
      });
    });
  }

  // Initial binding
  rebindTodoCheckboxes();

  // ==================== Prescription Form ====================
  var prescriptionForm = document.querySelector('.prescription-form');
  if (prescriptionForm) {
    prescriptionForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      var selects = prescriptionForm.querySelectorAll('select');
      var inputs = prescriptionForm.querySelectorAll('input[type="text"]');
      var textarea = prescriptionForm.querySelector('textarea');

      var userSelect = selects[0];
      var analysisSelect = selects[1];
      var ingredientSelect = selects[2];
      var frequencySelect = selects[3];

      var payload = {
        user_id: userSelect ? userSelect.value : '',
        analysis_id: analysisSelect ? analysisSelect.value : '',
        ingredient: ingredientSelect ? ingredientSelect.value : '',
        dosage: inputs[0] ? inputs[0].value : '',
        frequency: frequencySelect ? frequencySelect.value : '',
        instructions: textarea ? textarea.value : ''
      };

      var submitBtn = prescriptionForm.querySelector('button[type="submit"]');
      submitBtn.classList.add('loading');

      var result = await api('/api/v1/medications/prescribe', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      submitBtn.classList.remove('loading');

      if (result) {
        showSuccessToast('\u5904\u65B9\u5F00\u5177\u6210\u529F\uFF01\u60A3\u8005\u5C06\u6536\u5230\u7528\u836F\u63D0\u9192\u3002');
        prescriptionForm.reset();
      }
    });
  }

  // ==================== Window Resize ====================
  var resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (state.currentPage === 'dashboard') {
        initTrendChart();
        initConstitutionMiniChart();
      }
      if (state.currentPage === 'tcm') {
        initConstitutionRadarChart();
      }
      if (state.currentPage === 'repair') {
        if (state.demoMode) {
          drawRepairTrend(DEMO.repair.trend);
        } else if (state.cache.repair && state.cache.repair.trend) {
          drawRepairTrend(state.cache.repair.trend);
        }
      }
    }, 200);
  });

  // ==================== Plan Feedback UI ====================
  var _planFeedbackRating = 0;
  function initPlanFeedback() {
    var stars = document.querySelectorAll('#plan-feedback-stars .feedback-star');
    var textArea = document.getElementById('plan-feedback-text');
    var submitBtn = document.getElementById('plan-feedback-submit');
    if (!stars.length) return;
    stars.forEach(function(star) {
      star.addEventListener('click', function() {
        _planFeedbackRating = parseInt(this.dataset.rating);
        stars.forEach(function(s, i) {
          s.style.color = i < _planFeedbackRating ? '#fbbf24' : '#e5e7eb';
        });
        if (textArea) textArea.style.display = 'block';
        if (submitBtn) submitBtn.style.display = 'inline-block';
      });
    });
  }

  window.submitPlanFeedback = function() {
    var text = document.getElementById('plan-feedback-text');
    var textVal = text ? text.value : '';
    submitFeedback('plan-result-' + Date.now(), _planFeedbackRating, textVal);
    var submitBtn = document.getElementById('plan-feedback-submit');
    if (submitBtn) submitBtn.style.display = 'none';
    if (text) text.style.display = 'none';
    _planFeedbackRating = 0;
    var stars = document.querySelectorAll('#plan-feedback-stars .feedback-star');
    stars.forEach(function(s) { s.style.color = '#e5e7eb'; });
  };

  window.copyInviteCode = async function() {
    var data = await generateInviteCode();
    if (data && data.invite_code) {
      var el = document.getElementById('profile-invite-code');
      if (el) el.textContent = data.invite_code;
      try {
        await navigator.clipboard.writeText(data.invite_url || data.invite_code);
        showSuccessToast('邀请码已复制到剪贴板');
      } catch (e) {
        showSuccessToast('邀请码：' + data.invite_code);
      }
    }
  };

  window.shareAppLink = async function() {
    var data = await generateShareLink('app', null);
    if (data && data.share_url) {
      try {
        await navigator.clipboard.writeText(data.share_url);
        showSuccessToast('分享链接已复制到剪贴板');
      } catch (e) {
        showSuccessToast('分享链接：' + data.share_url);
      }
    }
  };

  // ==================== 购买积分 ====================
  var _buyPointsState = {
    polling: null,
    currentOrder: null,
    packages: [],
    payMethod: 'xunhu'  // 默认微信/支付宝（虎皮椒）
  };

  function showBuyStep(stepId) {
    ['buy-step-packages', 'buy-step-pay', 'buy-step-success', 'buy-step-error'].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    var el = document.getElementById(stepId);
    if (el) el.style.display = 'block';
  }

  async function loadPointsBalance() {
    try {
      // 直接fetch绕过demoMode
      var balToken = getAccessToken();
      var balResp = await fetch(API_BASE + '/api/v1/freemium/balance-info', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': balToken ? ('Bearer ' + balToken) : ''
        }
      });
      var balJson = await balResp.json();
      var data = (balJson && balJson.success) ? balJson.data : null;
      if (data && typeof data.balance !== 'undefined') {
        var bal = data.balance;
        var balEl = document.getElementById('buy-current-balance');
        if (balEl) balEl.textContent = bal;
        var profEl = document.getElementById('profile-points-balance');
        if (profEl) profEl.textContent = bal;
        var topEl = document.getElementById('topbar-points');
        if (topEl) topEl.textContent = bal + ' 积分';
      }
    } catch (e) {
      // 余额查询失败不阻塞流程
    }
  }

  async function loadPackages() {
    var listEl = document.getElementById('packages-list');
    if (!listEl) return;

    try {
      // 套餐API不需要认证，直接fetch绕过demoMode限制
      var pkgResp = await fetch(API_BASE + '/api/v1/growth/points/packages', {
        headers: { 'Content-Type': 'application/json' }
      });
      var pkgJson = await pkgResp.json();
      var packages = (pkgJson && pkgJson.success && Array.isArray(pkgJson.data)) ? pkgJson.data : [];

      if (!packages || packages.length === 0) {
        listEl.innerHTML = '<div style="grid-column:span 2;text-align:center;padding:2rem;color:var(--muted);font-size:0.9rem">暂无可用套餐</div>';
        return;
      }

      _buyPointsState.packages = packages;

      listEl.innerHTML = packages.map(function(pkg) {
        var popular = pkg.is_popular ? '<span style="position:absolute;top:-8px;right:8px;background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff;font-size:0.65rem;padding:2px 8px;border-radius:8px;font-weight:600">热门</span>' : '';
        var originalPrice = pkg.original_price ? '<span style="font-size:0.75rem;color:var(--muted);text-decoration:line-through;margin-left:0.3rem">¥' + pkg.original_price + '</span>' : '';
        var bonus = pkg.bonus_points > 0 ? '<span style="font-size:0.7rem;color:#f59e0b;margin-left:0.3rem">+' + pkg.bonus_points + '赠</span>' : '';
        return '<div style="position:relative;padding:1rem;border-radius:12px;border:2px solid ' + (pkg.is_popular ? 'var(--accent)' : 'var(--border)') + ';cursor:pointer;transition:all 0.2s" onclick="selectPackage(\'' + pkg.package_code + '\')" onmouseover="this.style.borderColor=\'var(--accent)\'" onmouseout="this.style.borderColor=\'' + (pkg.is_popular ? 'var(--accent)' : 'var(--border)') + '\'">' + popular +
          '<div style="font-size:0.85rem;font-weight:600;color:var(--ink)">' + pkg.package_name + '</div>' +
          '<div style="font-size:1.4rem;font-weight:800;color:var(--accent);margin:0.5rem 0">¥' + pkg.price_cny + originalPrice + '</div>' +
          '<div style="font-size:0.8rem;color:var(--ink-secondary)">' + pkg.points_amount + ' 积分' + bonus + '</div>' +
          '<div style="font-size:0.7rem;color:var(--muted);margin-top:0.4rem">' + (pkg.description || '') + '</div>' +
          '</div>';
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div style="grid-column:span 2;text-align:center;padding:2rem;color:var(--muted);font-size:0.9rem">套餐加载失败，请稍后重试</div>';
    }
  }

  // 支付方式选择
  window.selectPayMethod = function(method) {
    _buyPointsState.payMethod = method;
    // 高亮当前选中项，其余恢复默认边框
    ['xunhu', 'creem'].forEach(function(m) {
      var el = document.getElementById('pay-method-' + m);
      if (el) el.style.borderColor = (m === method) ? 'var(--accent)' : 'var(--border)';
    });
  };

  window.showBuyPoints = async function() {
    if (!isLoggedIn()) {
      showErrorToast('请先登录');
      return;
    }

    var modal = document.getElementById('buy-points-modal');
    if (modal) modal.classList.remove('hidden');

    showBuyStep('buy-step-packages');
    await Promise.all([loadPackages(), loadPointsBalance()]);
  };

  window.closeBuyPoints = function() {
    var modal = document.getElementById('buy-points-modal');
    if (modal) modal.classList.add('hidden');

    // 停止轮询
    if (_buyPointsState.polling) {
      clearInterval(_buyPointsState.polling);
      _buyPointsState.polling = null;
    }
    _buyPointsState.currentOrder = null;
  };

  window.resetBuyPoints = function() {
    if (_buyPointsState.polling) {
      clearInterval(_buyPointsState.polling);
      _buyPointsState.polling = null;
    }
    showBuyStep('buy-step-packages');
  };

  window.cancelPayment = function() {
    if (_buyPointsState.polling) {
      clearInterval(_buyPointsState.polling);
      _buyPointsState.polling = null;
    }
    _buyPointsState.currentOrder = null;
    showBuyStep('buy-step-packages');
  };

  window.selectPackage = async function(packageCode) {
    var pkg = _buyPointsState.packages.find(function(p) { return p.package_code === packageCode; });
    if (!pkg) {
      showErrorToast('套餐信息不存在');
      return;
    }

    var payMethod = _buyPointsState.payMethod || 'xunhu';

    // 虎皮椒支付：显示二维码
    // 显示支付步骤
    showBuyStep('buy-step-pay');
    var nameEl = document.getElementById('pay-package-name');
    if (nameEl) nameEl.textContent = pkg.package_name + ' (' + pkg.total_points + '积分)';
    var amtEl = document.getElementById('pay-amount');
    if (amtEl) amtEl.textContent = pkg.price_cny;
    var statusEl = document.getElementById('pay-status-text');
    if (statusEl) { statusEl.textContent = '正在创建支付订单...'; statusEl.style.color = 'var(--accent)'; }
    var qrEl = document.getElementById('qrcode-container');
    if (qrEl) qrEl.innerHTML = '<div style="width:180px;height:180px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">加载中...</div>';

    try {
      // 直接fetch绕过demoMode，购买API需要认证
      var token = getAccessToken();
      var buyResp = await fetch(API_BASE + '/api/v1/growth/points/buy?package_code=' + encodeURIComponent(packageCode) + '&payment_method=' + encodeURIComponent(payMethod), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? ('Bearer ' + token) : ''
        }
      });
      var buyJson = await buyResp.json();
      var data = (buyJson && buyJson.success) ? buyJson.data : null;

      if (!data) {
        showBuyStepError(buyJson.detail || buyJson.message || '创建订单失败，请稍后重试');
        return;
      }

      // 检查是否直接成功（mock支付）
      if (data.payment_status === 'paid' && data.points_credited) {
        showBuyStepSuccess(data.total_points || pkg.total_points);
        return;
      }

      // 获取支付链接和二维码
      var payUrl = data.pay_url || '';
      var qrcodeUrl = data.qrcode_url || '';
      var orderNo = data.order_no || '';

      if (!orderNo) {
        showBuyStepError('未获取到订单号');
        return;
      }

      _buyPointsState.currentOrder = orderNo;

      // 渲染二维码 / 国际信用卡支付入口
      var isCreem = (payMethod === 'creem' || payMethod === 'card' || payMethod === 'international');
      if (qrEl) {
        if (isCreem) {
          if (payUrl) {
            qrEl.innerHTML = '<div style="text-align:center;padding:0.5rem">' +
              '<div style="font-size:0.8rem;color:var(--muted);margin-bottom:0.6rem">国际信用卡支付（USD）</div>' +
              '<a href="' + payUrl + '" target="_blank" rel="noopener" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:12px 22px;border-radius:50px;text-decoration:none;font-weight:600;font-size:0.95rem">前往信用卡支付 ↗</a>' +
              '<div style="font-size:0.7rem;color:var(--muted);margin-top:0.6rem">支付完成后本页将自动到账</div>' +
              '</div>';
          } else {
            qrEl.innerHTML = '<div style="width:180px;height:180px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">未获取到支付链接</div>';
          }
        } else if (qrcodeUrl) {
          // 虎皮椒返回的二维码URL
          qrEl.innerHTML = '<img src="' + qrcodeUrl + '" width="180" height="180" alt="支付二维码" style="border-radius:8px" />';
        } else if (payUrl) {
          // 如果只有支付链接，生成二维码
          qrEl.innerHTML = '<img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=' + encodeURIComponent(payUrl) + '" width="180" height="180" alt="支付二维码" style="border-radius:8px" />';
        } else {
          qrEl.innerHTML = '<div style="width:180px;height:180px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:0.8rem">未获取到二维码</div>';
        }
      }

      if (statusEl) {
        statusEl.textContent = isCreem ? '请在新窗口完成信用卡支付（USD）' : '请使用微信/支付宝扫码支付';
        statusEl.style.color = 'var(--accent)';
      }

      // 开始轮询支付状态
      startPaymentPolling(orderNo);

    } catch (e) {
      showBuyStepError(e.message || '创建支付订单时出错');
    }
  };

  function startPaymentPolling(orderNo) {
    if (_buyPointsState.polling) {
      clearInterval(_buyPointsState.polling);
    }

    var attempts = 0;
    var maxAttempts = 150; // 5分钟超时 (2秒 * 150)

    _buyPointsState.polling = setInterval(async function() {
      attempts++;

      if (attempts > maxAttempts) {
        clearInterval(_buyPointsState.polling);
        _buyPointsState.polling = null;
        showBuyStepError('支付超时，请重新尝试');
        return;
      }

      try {
        // 直接fetch绕过demoMode，轮询支付状态
        var pollToken = getAccessToken();
        var pollResp = await fetch(API_BASE + '/api/v1/payment/status/' + encodeURIComponent(orderNo), {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': pollToken ? ('Bearer ' + pollToken) : ''
          }
        });
        var pollJson = await pollResp.json();
        var data = (pollJson && pollJson.success) ? pollJson.data : null;

        if (!data) return;

        if (data.payment_status === 'paid') {
          clearInterval(_buyPointsState.polling);
          _buyPointsState.polling = null;

          var points = data.total_points || 0;
          showBuyStepSuccess(points);

          // 刷新余额
          loadPointsBalance();
        }
      } catch (e) {
        // 静默处理轮询错误
      }
    }, 2000);
  }

  function showBuyStepSuccess(points) {
    showBuyStep('buy-step-success');
    var el = document.getElementById('success-points');
    if (el) el.textContent = points;
  }

  function showBuyStepError(message) {
    showBuyStep('buy-step-error');
    var el = document.getElementById('error-message');
    if (el) el.textContent = message || '请稍后重试';
  }

  // ==================== Initialization ====================
  async function init() {
    if (isLoggedIn()) {
      // Try to verify token and get current user
      var user = await loadCurrentUser();
      if (user) {
        showAppView();
      } else {
        // Token invalid, try refresh
        try {
          await refreshToken();
          showAppView();
        } catch (e) {
          // Refresh failed, show login
          showAppropriateView();
        }
      }
    } else {
      showAppropriateView();
    }

    // Period button click for trends page
    document.querySelectorAll('.period-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var period = parseInt(this.dataset.period);
        document.querySelectorAll('.period-btn').forEach(function(b) {
          b.classList.remove('active', 'btn-primary');
          b.classList.add('btn-ghost');
        });
        this.classList.add('active', 'btn-primary');
        this.classList.remove('btn-ghost');
        renderTrends(DEMO.trends, period);
      });
    });

    initPlanFeedback();
  }

  // ==================== Growth Center ====================
  async function loadGrowth(forceRefresh) {
    var container = document.getElementById('page-growth');
    if (!container) {
      container = document.querySelector('.page.active') || document.querySelector('.page');
      if (container) {
        var existing = container.querySelector('#growth-content');
        if (existing) existing.remove();
        var tempDiv = document.createElement('div');
        tempDiv.id = 'growth-content';
        container.insertBefore(tempDiv, container.firstChild);
        container = tempDiv;
      }
    }
    if (!container) return;
    container.id = 'page-growth';

    var data = state.demoMode ? DEMO.growth : (state.cache.growth || DEMO.growth);
    if (data && !forceRefresh) {
      state.cache.growth = data;
    }
    renderGrowth(data, container);
  }

  function renderGrowth(data, container) {
    if (!data || !container) return;
    var wr = data.weeklyReport || {};
    var achievements = data.achievements || [];
    var checkins = data.dailyCheckin || {};
    var progressPct = data.nextLevelPoints ? Math.min(100, Math.round((data.points / data.nextLevelPoints) * 100)) : 0;

    // Icon map for achievements
    var iconMap = { star: '\u2605', fire: '\uD83D\uDD25', moon: '\uD83C\uDF19', running: '\uD83C\uDFC3', heart: '\u2764' };

    // Build checkin calendar
    var checkinDates = Object.keys(checkins).sort().reverse();
    var checkinHtml = '';
    checkinDates.forEach(function (date) {
      var c = checkins[date];
      var done = (c.sleep && c.exercise && c.nutrition && c.checklist && c.tcm);
      var partial = (c.sleep || c.exercise || c.nutrition || c.checklist || c.tcm);
      var statusClass = done ? 'checkin-done' : (partial ? 'checkin-partial' : 'checkin-missed');
      var tags = [];
      if (c.sleep) tags.push('<span class="checkin-tag" style="background:#6366f1">\u7761</span>');
      if (c.exercise) tags.push('<span class="checkin-tag" style="background:#0d8a6a">\u52A8</span>');
      if (c.nutrition) tags.push('<span class="checkin-tag" style="background:#d97706">\u98DF</span>');
      if (c.checklist) tags.push('<span class="checkin-tag" style="background:#0284c7">\u6E05\u5355</span>');
      if (c.tcm) tags.push('<span class="checkin-tag" style="background:#7c3aed">\u4E2D\u533B</span>');
      checkinHtml += '<div class="checkin-day ' + statusClass + '">' +
        '<div class="checkin-date">' + date + '</div>' +
        '<div class="checkin-tags">' + tags.join('') + '</div>' +
        '</div>';
    });

    // Build achievements
    var achieveHtml = '';
    achievements.forEach(function (a) {
      var iconChar = iconMap[a.icon] || '\u2605';
      var unlockClass = a.unlocked ? 'achievement-unlocked' : 'achievement-locked';
      achieveHtml += '<div class="achievement-card ' + unlockClass + '">' +
        '<div class="achievement-icon">' + iconChar + '</div>' +
        '<div class="achievement-name">' + a.name + '</div>' +
        '<div class="achievement-desc">' + a.desc + '</div>' +
        (a.unlocked && a.date ? '<div class="achievement-date">' + a.date + ' \u89E3\u9501</div>' : '<div class="achievement-date">\u672A\u89E3\u9501</div>') +
        '</div>';
    });

    // Build suggestions
    var suggestionsHtml = '';
    (wr.suggestions || []).forEach(function (s) {
      suggestionsHtml += '<li>' + s + '</li>';
    });

    container.innerHTML =
      '<style>' +
      '.growth-container { padding: 4px 0; }' +
      '.growth-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }' +
      '.growth-level { display: flex; align-items: center; gap: 14px; }' +
      '.growth-level-badge { width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, #0d8a6a, #059669); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 700; box-shadow: 0 4px 12px rgba(13,138,106,0.3); }' +
      '.growth-level-info h3 { margin: 0 0 4px 0; font-size: 18px; color: #1a1a2e; }' +
      '.growth-level-info p { margin: 0; font-size: 13px; color: #888; }' +
      '.growth-stats-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }' +
      '.growth-stat-card { flex: 1; min-width: 100px; background: #f8f9fa; border-radius: 12px; padding: 14px; text-align: center; }' +
      '.growth-stat-card .gs-value { font-size: 22px; font-weight: 700; color: #1a1a2e; }' +
      '.growth-stat-card .gs-label { font-size: 12px; color: #888; margin-top: 4px; }' +
      '.growth-progress-bar { width: 100%; height: 8px; background: #e9ecef; border-radius: 4px; overflow: hidden; margin: 8px 0 4px 0; }' +
      '.growth-progress-fill { height: 100%; background: linear-gradient(90deg, #0d8a6a, #34d399); border-radius: 4px; transition: width 0.6s ease; }' +
      '.growth-section { margin-bottom: 24px; }' +
      '.growth-section-title { font-size: 16px; font-weight: 600; color: #1a1a2e; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #e9ecef; display: flex; align-items: center; gap: 8px; }' +
      '.weekly-report-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin-bottom: 16px; }' +
      '.weekly-metric { background: #f8f9fa; border-radius: 10px; padding: 12px; text-align: center; }' +
      '.weekly-metric .wm-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }' +
      '.weekly-metric .wm-value.improvement { color: #0d8a6a; }' +
      '.weekly-metric .wm-label { font-size: 12px; color: #888; margin-top: 4px; }' +
      '.weekly-top-action { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; font-size: 14px; color: #166534; border-left: 4px solid #0d8a6a; }' +
      '.weekly-suggestions { background: #fffbeb; border-radius: 10px; padding: 12px 16px; border-left: 4px solid #d97706; }' +
      '.weekly-suggestions ul { margin: 6px 0 0 0; padding-left: 18px; font-size: 13px; color: #92400e; }' +
      '.checkin-grid { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px; }' +
      '.checkin-day { min-width: 90px; background: #f8f9fa; border-radius: 10px; padding: 10px; text-align: center; flex-shrink: 0; }' +
      '.checkin-day.checkin-done { background: #f0fdf4; border: 1px solid #86efac; }' +
      '.checkin-day.checkin-partial { background: #fffbeb; border: 1px solid #fde68a; }' +
      '.checkin-day.checkin-missed { background: #fef2f2; border: 1px solid #fecaca; }' +
      '.checkin-date { font-size: 14px; font-weight: 600; color: #1a1a2e; margin-bottom: 6px; }' +
      '.checkin-tags { display: flex; gap: 4px; flex-wrap: wrap; justify-content: center; }' +
      '.checkin-tag { display: inline-block; width: 24px; height: 24px; border-radius: 50%; color: #fff; font-size: 10px; line-height: 24px; text-align: center; }' +
      '.achievements-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }' +
      '.achievement-card { background: #f8f9fa; border-radius: 12px; padding: 16px; text-align: center; transition: transform 0.2s, box-shadow 0.2s; }' +
      '.achievement-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }' +
      '.achievement-card.achievement-unlocked { background: linear-gradient(135deg, #f0fdf4, #dcfce7); }' +
      '.achievement-card.achievement-locked { opacity: 0.5; filter: grayscale(0.8); }' +
      '.achievement-icon { font-size: 28px; margin-bottom: 6px; }' +
      '.achievement-name { font-size: 14px; font-weight: 600; color: #1a1a2e; }' +
      '.achievement-desc { font-size: 12px; color: #888; margin-top: 4px; }' +
      '.achievement-date { font-size: 11px; color: #aaa; margin-top: 6px; }' +
      '</style>' +
      '<div class="growth-container">' +
        '<div class="growth-header">' +
          '<div class="growth-level">' +
            '<div class="growth-level-badge">Lv' + data.level + '</div>' +
            '<div class="growth-level-info">' +
              '<h3>' + data.levelName + '</h3>' +
              '<p>' + data.points + ' / ' + data.nextLevelPoints + ' \u79EF\u5206</p>' +
              '<div class="growth-progress-bar"><div class="growth-progress-fill" style="width:' + progressPct + '%"></div></div>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="growth-stats-row">' +
          '<div class="growth-stat-card"><div class="gs-value" style="color:#ff6b00">' + data.streak + '</div><div class="gs-label">\u8FDE\u7EED\u6253\u5361\u5929\u6570</div></div>' +
          '<div class="growth-stat-card"><div class="gs-value">' + data.totalDays + '</div><div class="gs-label">\u7D2F\u8BA1\u6253\u5361\u5929\u6570</div></div>' +
          '<div class="growth-stat-card"><div class="gs-value" style="color:#0d8a6a">' + data.points + '</div><div class="gs-label">\u5F53\u524D\u79EF\u5206</div></div>' +
        '</div>' +
        '<div class="growth-section">' +
          '<div class="growth-section-title">\uD83D\uDCCA \u5468\u62A5\u544A (' + (wr.weekStart || '') + ' ~ ' + (wr.weekEnd || '') + ')</div>' +
          '<div class="weekly-report-grid">' +
            '<div class="weekly-metric"><div class="wm-value">' + (wr.checkins || 0) + '/7</div><div class="wm-label">\u6253\u5361\u5929\u6570</div></div>' +
            '<div class="weekly-metric"><div class="wm-value">' + (wr.sleepAvg || 0) + '</div><div class="wm-label">\u7761\u7720\u5747\u5206</div></div>' +
            '<div class="weekly-metric"><div class="wm-value">' + (wr.exerciseCount || 0) + '</div><div class="wm-label">\u8FD0\u52A8\u6B21\u6570</div></div>' +
            '<div class="weekly-metric"><div class="wm-value">' + (wr.nutritionScore || 0) + '</div><div class="wm-label">\u8425\u517B\u8BC4\u5206</div></div>' +
            '<div class="weekly-metric"><div class="wm-value improvement">' + (wr.improvement || '+0') + '</div><div class="wm-label">\u7EFC\u5408\u63D0\u5347</div></div>' +
          '</div>' +
          (wr.topAction ? '<div class="weekly-top-action">\u2605 \u672C\u5468\u4EAE\u70B9\uFF1A' + wr.topAction + '</div>' : '') +
          (suggestionsHtml ? '<div class="weekly-suggestions"><strong>\uD83D\uDCDD \u5EFA\u8BAE</strong><ul>' + suggestionsHtml + '</ul></div>' : '') +
        '</div>' +
        '<div class="growth-section">' +
          '<div class="growth-section-title">\uD83D\uDCC5 \u6253\u5361\u65E5\u5386</div>' +
          '<div class="checkin-grid">' + checkinHtml + '</div>' +
        '</div>' +
        '<div class="growth-section">' +
          '<div class="growth-section-title">\uD83C\uDFC6 \u6210\u5C31\u5FBD\u7AE0</div>' +
          '<div class="achievements-grid">' + achieveHtml + '</div>' +
        '</div>' +
      '</div>';
  }

  // ==================== Today Page ====================
  async function loadToday(forceRefresh) {
    if (state.demoMode || !state.token) {
      state.demoMode = true;
      renderToday(DEMO.today);
    } else {
      // API integration
      renderToday(DEMO.today);
    }
  }

  function renderToday(data) {
    // Render timeline
    var timelineContainer = document.getElementById('today-timeline');
    if (timelineContainer && data.timeline) {
      var html = '';
      data.timeline.forEach(function(node) {
        var tagHtml = node.tags.map(function(t) {
          var labels = { sleep: '睡眠', nutrition: '营养', exercise: '运动', frequency: '五音', food_med: '药食' };
          var colors = { sleep: 'rgba(96,165,250,0.15);color:#60a5fa', nutrition: 'rgba(74,222,128,0.15);color:#4ade80', exercise: 'rgba(251,191,36,0.15);color:#fbbf24', frequency: 'rgba(244,114,182,0.15);color:#f472b6', food_med: 'rgba(167,139,250,0.15);color:#a78bfa' };
          return '<span class="timeline-tag" style="background:' + colors[t].split(';')[0] + ';' + colors[t].split(';')[1] + '">' + (labels[t] || t) + '</span>';
        }).join('');
        html += '<div class="timeline-node">' +
          '<div class="timeline-time">' + node.time + '</div>' +
          '<div class="timeline-content">' + node.items.join(' · ') + '</div>' +
          '<div class="timeline-tags">' + tagHtml + '</div>' +
          '</div>';
      });
      timelineContainer.innerHTML = html;
    }

    // Render metrics
    var metricsContainer = document.getElementById('today-metrics');
    if (metricsContainer && data.metrics) {
      metricsContainer.innerHTML = data.metrics.map(function(m) {
        var trendIcon = m.trend.startsWith('+') ? '&#9650;' : '&#9660;';
        var trendColor = m.trend.startsWith('+') ? '#4ade80' : '#f87171';
        return '<div class="card" style="padding:1rem;text-align:center;border-radius:12px">' +
          '<div style="font-size:0.75rem;color:var(--muted)">' + m.label + '</div>' +
          '<div style="font-size:1.5rem;font-weight:800;color:' + m.color + ';margin:0.25rem 0">' + m.value + '<span style="font-size:0.7rem;font-weight:400;color:var(--muted)">' + m.unit + '</span></div>' +
          '<div style="font-size:0.75rem;color:' + trendColor + '">' + trendIcon + ' ' + m.trend + '</div>' +
          '</div>';
      }).join('');
    }

    // Score breakdown (sub-scores)
    var scoreBreakdown = document.getElementById('score-breakdown');
    if (scoreBreakdown) {
      var subScores = [
        { label: '深睡', value: 84, weight: 25, color: '#60a5fa' },
        { label: 'HRV', value: 72, weight: 20, color: '#a78bfa' },
        { label: '炎症', value: 65, weight: 15, color: '#f87171' },
        { label: '运动', value: 78, weight: 15, color: '#fbbf24' },
        { label: '营养', value: 80, weight: 10, color: '#4ade80' },
        { label: '节律', value: 70, weight: 10, color: '#f472b6' },
        { label: '精力', value: 68, weight: 5, color: '#38bdf8' }
      ];
      scoreBreakdown.innerHTML = subScores.map(function(s) {
        return '<div class="card" style="padding:0.6rem 0.8rem;border-radius:10px;display:flex;align-items:center;gap:0.5rem">' +
          '<div style="flex:1;font-size:0.78rem;color:var(--ink)">' + s.label + '</div>' +
          '<div style="width:60px;height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden">' +
            '<div style="width:' + s.value + '%;height:100%;background:' + s.color + ';border-radius:3px;transition:width 0.6s"></div>' +
          '</div>' +
          '<div style="font-size:0.78rem;font-weight:600;color:' + s.color + ';min-width:28px;text-align:right">' + s.value + '</div>' +
          '<div style="font-size:0.65rem;color:var(--muted);min-width:20px;text-align:right">' + s.weight + '%</div>' +
          '</div>';
      }).join('');
    }
  }

  // ==================== Trends Page ====================
  async function loadTrends(forceRefresh) {
    renderTrends(DEMO.trends, 7);
  }

  function renderTrends(data, period) {
    period = period || 7;
    var dates = data['dates' + period] || data.dates7;
    var scores = data['scores' + period] || data.scores7;
    var ages = data['ages' + period] || data.ages7;

    // Score trend chart
    drawTrendLine('trend-score-chart', dates, scores, '#10b981', '修复评分', 40, 100);

    // Age trend chart
    var calendarAge = 54;
    drawTrendDualLine('trend-age-chart', dates, ages, calendarAge, '修复年龄', '日历年龄');

    // Dimension cards
    var dimContainer = document.getElementById('trend-dimensions');
    if (dimContainer && data.dimensions) {
      dimContainer.innerHTML = data.dimensions.map(function(d) {
        var trendIcon = d.trend.startsWith('+') ? '&#9650;' : '&#9660;';
        var trendColor = d.trend.startsWith('+') ? '#4ade80' : '#f87171';
        return '<div class="card" style="padding:1rem;border-radius:12px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">' +
          '<span style="font-size:0.85rem;color:var(--ink-secondary)">' + d.name + '</span>' +
          '<span style="font-size:0.75rem;color:' + trendColor + '">' + trendIcon + ' ' + d.trend + '</span></div>' +
          '<div style="font-size:1.25rem;font-weight:700;color:' + d.color + '">' + d.score + '</div>' +
          '<div style="height:4px;background:rgba(255,255,255,0.06);border-radius:2px;margin-top:0.5rem;overflow:hidden">' +
          '<div style="height:100%;width:' + d.score + '%;background:' + d.color + ';border-radius:2px"></div></div>' +
          '</div>';
      }).join('');
    }
  }

  function drawTrendLine(containerId, dates, values, color, label, minV, maxV) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var W = container.clientWidth || 600;
    var H = container.clientHeight || 200;
    var pad = { top: 20, right: 15, bottom: 30, left: 35 };
    var cw = W - pad.left - pad.right;
    var ch = H - pad.top - pad.bottom;

    var points = values.map(function(v, i) {
      return {
        x: pad.left + (i / (values.length - 1)) * cw,
        y: pad.top + ch - ((v - minV) / (maxV - minV)) * ch
      };
    });

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:' + H + 'px">';
    for (var g = 0; g <= 4; g++) {
      var gy = pad.top + (g / 4) * ch;
      svg += '<line x1="' + pad.left + '" y1="' + gy + '" x2="' + (W - pad.right) + '" y2="' + gy + '" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>';
      svg += '<text x="' + (pad.left - 6) + '" y="' + (gy + 4) + '" text-anchor="end" font-size="10" fill="#64748b">' + Math.round(maxV - (g / 4) * (maxV - minV)) + '</text>';
    }
    var areaPath = 'M' + points[0].x + ',' + points[0].y;
    points.forEach(function(p) { areaPath += ' L' + p.x + ',' + p.y; });
    areaPath += ' L' + points[points.length - 1].x + ',' + (pad.top + ch) + ' L' + points[0].x + ',' + (pad.top + ch) + ' Z';
    svg += '<path d="' + areaPath + '" fill="' + color + '" opacity="0.1"/>';
    var linePath = 'M' + points[0].x + ',' + points[0].y;
    points.forEach(function(p, i) { if (i > 0) linePath += ' L' + p.x + ',' + p.y; });
    svg += '<path d="' + linePath + '" fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
    points.forEach(function(p, i) {
      svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="4" fill="' + color + '" stroke="#0f172a" stroke-width="2"/>';
      svg += '<text x="' + p.x + '" y="' + (pad.top + ch + 18) + '" text-anchor="middle" font-size="9" fill="#64748b">' + dates[i] + '</text>';
    });
    svg += '</svg>';
    container.innerHTML = svg;
  }

  function drawTrendDualLine(containerId, dates, values, refValue, label1, label2) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var W = container.clientWidth || 600;
    var H = container.clientHeight || 180;
    var pad = { top: 20, right: 15, bottom: 30, left: 35 };
    var cw = W - pad.left - pad.right;
    var ch = H - pad.top - pad.bottom;
    var allVals = values.concat([refValue]);
    var minV = Math.min.apply(null, allVals) - 2;
    var maxV = Math.max.apply(null, allVals) + 2;

    var pts = values.map(function(v, i) {
      return { x: pad.left + (i / (values.length - 1)) * cw, y: pad.top + ch - ((v - minV) / (maxV - minV)) * ch };
    });
    var refY = pad.top + ch - ((refValue - minV) / (maxV - minV)) * ch;

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:' + H + 'px">';
    for (var g = 0; g <= 4; g++) {
      var gy = pad.top + (g / 4) * ch;
      svg += '<line x1="' + pad.left + '" y1="' + gy + '" x2="' + (W - pad.right) + '" y2="' + gy + '" stroke="rgba(255,255,255,0.05)" stroke-width="1"/>';
      svg += '<text x="' + (pad.left - 6) + '" y="' + (gy + 4) + '" text-anchor="end" font-size="10" fill="#64748b">' + Math.round(maxV - (g / 4) * (maxV - minV)) + '</text>';
    }
    svg += '<line x1="' + pad.left + '" y1="' + refY + '" x2="' + (W - pad.right) + '" y2="' + refY + '" stroke="#64748b" stroke-width="1" stroke-dasharray="4,4"/>';
    svg += '<text x="' + (W - pad.right + 3) + '" y="' + (refY + 3) + '" font-size="9" fill="#64748b">' + label2 + '</text>';
    var lp = 'M' + pts[0].x + ',' + pts[0].y;
    pts.forEach(function(p, i) { if (i > 0) lp += ' L' + p.x + ',' + p.y; });
    svg += '<path d="' + lp + '" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round"/>';
    var ap = 'M' + pts[0].x + ',' + pts[0].y;
    pts.forEach(function(p, i) { if (i > 0) ap += ' L' + p.x + ',' + p.y; });
    ap += ' L' + pts[pts.length - 1].x + ',' + (pad.top + ch) + ' L' + pts[0].x + ',' + (pad.top + ch) + ' Z';
    svg += '<path d="' + ap + '" fill="#10b981" opacity="0.08"/>';
    pts.forEach(function(p, i) {
      svg += '<circle cx="' + p.x + '" cy="' + p.y + '" r="3.5" fill="#10b981" stroke="#0f172a" stroke-width="2"/>';
      svg += '<text x="' + p.x + '" y="' + (pad.top + ch + 18) + '" text-anchor="middle" font-size="9" fill="#64748b">' + dates[i] + '</text>';
    });
    svg += '<text x="' + (W - pad.right - 30) + '" y="15" font-size="9" fill="#10b981">' + label1 + '</text>';
    svg += '</svg>';
    container.innerHTML = svg;
  }

  init();

})();

// === HealthLens loaded marker ===
window.__healthlens_loaded = true;
