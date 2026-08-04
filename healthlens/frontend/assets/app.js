/**
 * HealthLens Frontend Application
 * Integrated with HealthLens Backend API
 */

(function () {
  'use strict';

  // ==================== Configuration ====================
  const API_BASE = window.location.origin;  // 同源部署时自动使用当前域名

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
      background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
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
    user: { id: 1, name: '\u5F20\u5C0F\u660E', email: 'patient@demo.com', role: 'patient' },
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
    doctorReviews: [
      { id: 1, patient_name: '\u674E\u5EFA\u56FD', patient_avatar: '\u674E', gender: '\u7537', age: 58, date: '2026-07-20', diagnosis: '2\u578B\u7CD6\u5C3F\u75C5 (ICD-11: 5A11)', confidence: 87 },
      { id: 2, patient_name: '\u738B\u79C0\u82B3', patient_avatar: '\u738B', gender: '\u5973', age: 45, date: '2026-07-20', diagnosis: '\u9AD8\u8102\u8840\u75C7 (ICD-11: 5C70)', confidence: 92 },
      { id: 3, patient_name: '\u9648\u4F1F', patient_avatar: '\u9648', gender: '\u7537', age: 35, date: '2026-07-19', diagnosis: '\u9AD8\u8840\u538B (ICD-11: BA00)', confidence: 78 }
    ],
    doctorStats: { pending: 24, today_prescriptions: 8, my_patients: 156, accuracy: '92%' }
  };

  // ==================== DOM Elements ====================
  var landingView = document.getElementById('landing-view');
  var authModal = document.getElementById('auth-modal');
  var appView = document.getElementById('app-view');
  var loginForm = document.getElementById('login-form');
  var registerForm = document.getElementById('register-form');
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
    if (roleEl) roleEl.textContent = user.role === 'doctor' ? '\u533B\u751F' : '\u60A3\u8005';
    if (avatarEl) avatarEl.textContent = (user.name || user.username || '\u7528\u6237').charAt(0);

    // Show/hide doctor nav item based on role
    var doctorNav = document.querySelector('.nav-item[data-page="doctor"]');
    if (doctorNav) {
      doctorNav.style.display = (user.role === 'doctor') ? '' : 'none';
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
    setTimeout(function () {
      loadPageData('dashboard');
    }, 100);
  }

  // Open auth modal (login or register tab)
  function openAuthModal(tab) {
    authModal.classList.remove('hidden');
    authTabs.forEach(function (t) { t.classList.remove('active'); });
    if (tab === 'register') {
      authTabs[1].classList.add('active');
      loginForm.classList.remove('active');
      registerForm.classList.add('active');
    } else {
      authTabs[0].classList.add('active');
      loginForm.classList.add('active');
      registerForm.classList.remove('active');
    }
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

  function switchPage(page) {
    pages.forEach(function (p) { p.classList.remove('active'); });
    var target = document.getElementById('page-' + page);
    if (target) {
      target.classList.add('active');
      var titleEl = document.querySelector('.page-title');
      if (titleEl) titleEl.textContent = getPageTitle(page);
      state.currentPage = page;
      loadPageData(page);
    }
  }

  function getPageTitle(page) {
    var titles = {
      dashboard: '\u5065\u5EB7\u4EEA\u8868\u76D8',
      records: '\u5065\u5EB7\u6863\u6848',
      tcm: '\u4E2D\u533B\u4F53\u8D28',
      food: '\u98DF\u7597\u65B9\u6848',
      nonpharma: '\u975E\u836F\u7269\u6CBB\u7597',
      risk: '\u98CE\u9669\u8BC4\u4F30',
      doctor: '\u533B\u751F\u5DE5\u4F5C\u53F0'
    };
    return titles[page] || 'HealthLens';
  }

  // ==================== Page Data Loading ====================
  async function loadPageData(page, forceRefresh) {
    switch (page) {
      case 'dashboard':
        await loadDashboard(forceRefresh);
        break;
      case 'records':
        await loadRecords(forceRefresh);
        break;
      case 'tcm':
        await loadTCM(forceRefresh);
        break;
      case 'food':
        await loadFood(forceRefresh);
        break;
      case 'nonpharma':
        await loadNonPharma(forceRefresh);
        break;
      case 'risk':
        await loadRisk(forceRefresh);
        break;
      case 'doctor':
        await loadDoctor(forceRefresh);
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
      '  <button class="btn btn-primary" id="btn-ai-diagnosis">\u67E5\u770BAI\u8BCA\u65AD</button>' +
      '  <button class="btn btn-secondary">\u5BFC\u51FAPDF</button>' +
      '  <button class="btn btn-ghost">\u5206\u4EAB\u533B\u751F</button>' +
      '</div>';

    // Bind AI diagnosis button
    var aiBtn = document.getElementById('btn-ai-diagnosis');
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

  // ==================== Doctor Workstation ====================
  async function loadDoctor(forceRefresh) {
    if (state.demoMode) {
      renderDoctorStats(DEMO.doctorStats);
      renderDoctorReviews(DEMO.doctorReviews);
      return;
    }

    if (state.cache.doctor && !forceRefresh) {
      renderDoctorStats(state.cache.doctor.stats);
      renderDoctorReviews(state.cache.doctor.reviews);
      return;
    }

    // Load pending reviews and stats in parallel
    var reviewsPromise = api('/api/v1/diagnosis/results?status=pending');
    var statsPromise = api('/api/v1/dashboard/overview', { silent: true });

    var reviewsData = await reviewsPromise;
    var statsData = await statsPromise;

    var reviews = (reviewsData && reviewsData.results) ? reviewsData.results : (reviewsData || DEMO.doctorReviews);
    var stats = (statsData && statsData.doctor_stats) ? statsData.doctor_stats : DEMO.doctorStats;

    state.cache.doctor = { reviews: reviews, stats: stats };
    renderDoctorStats(stats);
    renderDoctorReviews(reviews);
  }

  function renderDoctorStats(stats) {
    if (!stats) return;
    var statCards = document.querySelectorAll('.stat-card .stat-number');
    var keys = ['pending', 'today_prescriptions', 'my_patients', 'accuracy'];
    statCards.forEach(function (el, i) {
      if (keys[i] && stats[keys[i]] !== undefined) {
        el.textContent = stats[keys[i]];
      }
    });
  }

  function renderDoctorReviews(reviews) {
    var container = document.querySelector('.review-list');
    if (!container) return;
    if (!reviews || reviews.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">\u6682\u65E0\u5F85\u5BA1\u6838\u8BCA\u65AD</div></div>';
      return;
    }
    var html = '';
    reviews.forEach(function (r) {
      var patientName = r.patient_name || '\u672A\u77E5\u60A3\u8005';
      var avatar = r.patient_avatar || patientName.charAt(0);
      var gender = r.gender || '\u7537';
      var age = r.age || '';
      var date = r.created_at || r.date || '';
      var diagnosis = r.ai_diagnosis || r.diagnosis || r.summary || '\u672A\u77E5\u8BCA\u65AD';
      var confidence = r.confidence || r.ai_confidence || 0;

      html +=
        '<div class="review-item" data-review-id="' + r.id + '">' +
        '  <div class="review-patient">' +
        '    <div class="patient-avatar">' + escapeHtml(avatar) + '</div>' +
        '    <div class="patient-info">' +
        '      <span class="patient-name">' + escapeHtml(patientName) + '</span>' +
        '      <span class="patient-meta">' + escapeHtml(gender) + ' \u00B7 ' + escapeHtml(age + '\u5C81') + ' \u00B7 ' + escapeHtml(date) + '</span>' +
        '    </div>' +
        '  </div>' +
        '  <div class="review-diagnosis">' +
        '    <span class="ai-diagnosis">AI\u8BCA\u65AD: ' + escapeHtml(diagnosis) + '</span>' +
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

      var patientSelect = selects[0];
      var diagnosisSelect = selects[1];
      var medicationSelect = selects[2];
      var frequencySelect = selects[3];

      var payload = {
        patient_id: patientSelect ? patientSelect.value : '',
        diagnosis_id: diagnosisSelect ? diagnosisSelect.value : '',
        medication: medicationSelect ? medicationSelect.value : '',
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
    }, 200);
  });

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
  }

  init();

})();

// === HealthLens loaded marker ===
window.__healthlens_loaded = true;
