// HealthLens _worker.js — Cloudflare Pages「高级模式」入口
//
// 背景：项目是 Direct Upload 部署，wrangler pages deploy 只上传静态资源，
// 原 functions/ 目录不会被编译成 Pages Functions（验证过 /api/v1/health 返回 SPA HTML）。
// 用 _worker.js 替代 functions/ 目录，即可让路由逻辑在 Workers 运行时真正执行。
//
// 路由策略（静态优先，避免破坏已上线的 SEO 成果）：
//   1. GET  /api/v1/growth/points/packages  -> 转发后端，失败回退静态套餐数据（edge-fallback）
//   2. POST /api/v1/growth/points/buy        -> 解析支付方式后转发后端创建订单
//   3. /api/**                               -> 全量反向代理到 BACKEND_URL（含支付 webhook/notify）
//   4. /knowledge/** /health/** /health-tools/** -> 静态优先（已生成的 SEO 页），缺失再代理（动态 613 页）
//   5. /sitemap.xml /llms.txt /ai.txt /robots.txt /humans.txt -> 静态 GEO 文件（不走代理，保证 SEO 始终可用）
//   6. 其它（首页/JS/CSS/图片）             -> 静态资源，SPA 回退 index.html
//
// 环境变量：
//   BACKEND_URL  FastAPI 源站地址（如 https://api.healthlens.cc）。【必填，不能填本站域名否则回环】

const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "transfer-encoding", "upgrade",
  "proxy-authenticate", "proxy-authorization", "te", "trailer", "host", "content-length",
]);

const SUPPORTED_METHODS = ["xunhu", "wechat", "alipay", "creem", "card", "international", "mock"];

function base64UrlDecode(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 ? 4 - (s.length % 4) : 0;
  s += "=".repeat(pad);
  return atob(s);
}

function json(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// 反向代理到 BACKEND_URL，保留原始 method/headers/query/body（Creem/虎皮椒 签名校验依赖原始字节）
async function proxy(request, env, url) {
  const backend = env.BACKEND_URL;
  if (!backend) {
    return json(503, { success: false, message: "后端未配置：请在 Cloudflare Pages 环境变量中设置 BACKEND_URL 指向 FastAPI 源站。" });
  }
  let backendUrl;
  try {
    backendUrl = new URL(backend);
  } catch (e) {
    return json(503, { success: false, message: "BACKEND_URL 不是合法的 URL。" });
  }
  // 防回环：BACKEND_URL 指向自己会造成无限递归
  if (backendUrl.host === url.host) {
    return json(503, { success: false, message: "BACKEND_URL 不能指向本站域名（会造成回环）。请填写后端源站地址。" });
  }

  const target = backendUrl.origin + url.pathname + (url.search || "");
  const headers = new Headers();
  for (const [k, v] of request.headers) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set("X-Forwarded-Host", url.host);
  headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
  // 关键修复：强制 Host 为后端域名。否则 Cloudflare 边缘会按原请求 Host(healthlens.cc)
  // 把 /api/** 子请求路由回 Pages 项目自身（静态层），找不到资源返回 404 空体，
  // 前端 resp.json() 解析空体即报 "Unexpected end of JSON input"。
  // handlePackages/handleBuy 默认用 target host(api.healthlens.cc) 故正常；此处对齐。
  headers.set("Host", backendUrl.host);

  const method = request.method.toUpperCase();
  // 直连源站 IP，绕过 Cloudflare 代理/WAF/回环（resolveOverride 是 Cloudflare Workers 原生能力）
  const ORIGIN_IP = env.BACKEND_ORIGIN_IP || "150.158.119.19";
  const init = { method, headers, redirect: "manual", cf: { resolveOverride: ORIGIN_IP } };
  if (!["GET", "HEAD"].includes(method)) {
    init.body = await request.arrayBuffer();
  }

  try {
    const resp = await fetch(target, init);
    const respHeaders = new Headers();
    for (const [k, v] of resp.headers) {
      if (!HOP_BY_HOP.has(k.toLowerCase())) respHeaders.set(k, v);
    }
    return new Response(resp.body, { status: resp.status, headers: respHeaders });
  } catch (e) {
    return json(502, { success: false, message: "后端不可达：" + e.message });
  }
}

// 支付下单：解析 JWT 中的 user_id（仅日志用），转发后端创建订单
async function handleBuy(request, env, url) {
  const method = (url.searchParams.get("payment_method") || "xunhu").toLowerCase();
  if (!SUPPORTED_METHODS.includes(method)) {
    return json(400, { success: false, message: "不支持的支付方式。国内请使用微信/支付宝，海外请使用信用卡（creem）。" });
  }
  const auth = request.headers.get("Authorization") || "";
  if (!auth) {
    return json(401, { success: false, message: "请先登录后再购买。" });
  }
  const backend = env.BACKEND_URL;
  if (!backend) {
    return json(503, { success: false, message: "支付通道未配置：请在 Cloudflare 环境变量设置 BACKEND_URL（后端源站地址）。" });
  }
  const target = backend.replace(/\/$/, "") + "/api/v1/growth/points/buy?" + url.searchParams.toString();
  try {
    const fwd = await fetch(target, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      cf: { resolveOverride: env.BACKEND_ORIGIN_IP || "150.158.119.19" },
    });
    const text = await fwd.text();
    return new Response(text, {
      status: fwd.status,
      headers: { "content-type": fwd.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return json(502, { success: false, message: "转发后端失败：" + e.message });
  }
}

// 套餐列表：后端单一事实来源，不可达时回退与后端一致的静态数据
const FALLBACK_PACKAGES = [
  { package_code: "starter", package_name: "体验包", price_cny: 9.9, points_amount: 100, total_points: 100, is_popular: false, description: "1 次完整报告解析（五层因果链 + 基础食养方案）", bonus_points: 0, original_price: 0 },
  { package_code: "basic", package_name: "进阶包", price_cny: 39, points_amount: 550, total_points: 600, is_popular: true, description: "5 次解析 + 风险分层 + 频率修复 + 方案反馈", bonus_points: 50, original_price: 49 },
  { package_code: "pro", package_name: "专业包", price_cny: 128, points_amount: 2300, total_points: 2500, is_popular: false, description: "23 次深度基因代谢解读 + 顾问优先响应", bonus_points: 200, original_price: 158 },
  { package_code: "ultimate", package_name: "旗舰包", price_cny: 299, points_amount: 6000, total_points: 6600, is_popular: false, description: "60 次解析 + 家庭共享(3人) + 全年健康档案", bonus_points: 600, original_price: 399 },
];

async function handlePackages(request, env) {
  const backend = env.BACKEND_URL;
  if (backend) {
    try {
      const fwd = await fetch(backend.replace(/\/$/, "") + "/api/v1/growth/points/packages", {
        headers: { "Content-Type": "application/json" },
        cf: { resolveOverride: env.BACKEND_ORIGIN_IP || "150.158.119.19" },
      });
      if (fwd.ok) {
        const text = await fwd.text();
        return new Response(text, {
          status: fwd.status,
          headers: { "content-type": fwd.headers.get("content-type") || "application/json", "cache-control": "public, max-age=60" },
        });
      }
    } catch (e) { /* 落到静态兜底 */ }
  }
  return json(200, { success: true, data: FALLBACK_PACKAGES, source: "edge-fallback" });
}

// 静态资源优先；对无扩展名路径尝试补 .html（Pages 干净 URL）
async function serveStatic(request, env, url) {
  let r = await env.ASSETS.fetch(request);
  if (r && r.status < 400) return r;
  const p = url.pathname;
  if (!p.endsWith(".html") && !p.endsWith("/")) {
    const alt = await env.ASSETS.fetch(new Request(url.origin + p + ".html"));
    if (alt && alt.status < 400) return alt;
  }
  return r; // 可能 404
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 1. 套餐列表（GET，带静态兜底）
    if (path === "/api/v1/growth/points/packages" && request.method === "GET") {
      return handlePackages(request, env);
    }
    // 2. 支付下单（POST）
    if (path === "/api/v1/growth/points/buy" && request.method === "POST") {
      return handleBuy(request, env, url);
    }
    // 3. /api/** 全量代理
    if (path.startsWith("/api/")) {
      return proxy(request, env, url);
    }
    // 3a. 裸 /health —— 对外暴露后端健康态，供监控/探测使用。
    // 根因：api.healthlens.cc 的 Cloudflare 边缘规则仅放行 /api/**，裸 /health 在边缘被 404，
    // 而源站 127.0.0.1:8000/health 实际健康。为不依赖 Cloudflare 控制台变更，这里降级为
    // 「经已放行的 /api 通道探活并合成健康态」：
    //   1) 优先尝试真实后端 /health（若边缘日后放行即直出真实健康 JSON）；
    //   2) 被拦截则探活公开端点 /api/v1/growth/points/packages，存活则合成 {"status":"ok",...}；
    //   3) 探活失败则 503 backend_unreachable。
    if (path === "/health") {
      const backend = (env.BACKEND_URL || "https://api.healthlens.cc").replace(/\/$/, "");
      // 1) 优先尝试真实后端 /health（若边缘日后放行则直出真实健康 JSON）
      try {
        const real = await fetch(backend + "/health", {
          headers: { "Content-Type": "application/json" },
          cf: { resolveOverride: env.BACKEND_ORIGIN_IP || "150.158.119.19" },
        });
        if (real && real.status >= 200 && real.status < 300) {
          const body = await real.text();
          return new Response(body, {
            status: 200,
            headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
          });
        }
      } catch (e) { /* 落到 /api 探活 */ }
      // 2) 经 /api 通道探活：复用 handlePackages（真后端数据 vs edge-fallback 静态兜底）
      const live = await handlePackages(request, env);
      const liveText = await live.text();
      const reachable = live.status >= 200 && live.status < 300 && !liveText.includes('"source":"edge-fallback"');
      if (reachable) {
        return new Response(JSON.stringify({
          status: "ok",
          version: "0.18.1",
          backend_reachable: true,
          checked_via: "/api (edge-allowed tunnel)",
          note: "Cloudflare edge blocks raw /health; health synthesized from /api liveness probe",
          timestamp: new Date().toISOString(),
        }), { status: 200, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
      }
      // 3) 边缘无法触达后端：api.healthlens.cc zone 拦截所有路径（404），后端仅 ECS localhost 可达；
      //    /api 当前由静态兜底服务。HTTP 200 保证端点可解析，消费方应看 backend_reachable 字段。
      //    修复：放宽 api.healthlens.cc zone 防火墙/边缘规则（方案 A）。
      return new Response(JSON.stringify({
        status: "degraded",
        backend_reachable: false,
        note: "api.healthlens.cc edge blocks all paths (404); backend reachable only via ECS localhost. /api served from static fallback. Fix: relax api.healthlens.cc zone firewall/edge rule (Plan A).",
        timestamp: new Date().toISOString(),
      }), { status: 200, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
    }
    // 3b. /app/** —— React SPA 产品入口（构建自 frontend/，vite base=/app/）
    // 关键：路由回退必须指向 /app/index.html。若退回根 index.html，
    // Pages 的 SPA 回退会把内容型 GEO 首页顶到 /app/* 上（产品白屏 + SEO 串页）。
    if (path === "/app" || path.startsWith("/app/")) {
      // 【2026-09-07 事故加固】资源类 URL（/app/assets/* 或带静态扩展名）绝不能
      // 返回 HTML：Pages 对未命中路径会 SPA 回退成根 index.html 且 status=200，
      // 于是 HTML 以 .js/.css 的 URL 被 CDN 按 max-age=14400 缓存 —— 真实表现为
      // 「源站 pages.dev 一切正常，自定义域却把 JS 当 HTML 吐」，React 永久白屏，
      // 且只能等 4 小时 TTL 过期（Pages-only 令牌无 Cache Purge 权限）。
      // 故：资源 URL 命中真实静态文件才直返，否则一律 404 + no-store，杜绝缓存投毒。
      const isAsset = path.includes("/assets/")
        || /\.(js|mjs|css|map|json|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot)$/i.test(path);
      const direct = await env.ASSETS.fetch(request);
      if (isAsset) {
        const ct = (direct && direct.headers.get("content-type")) || "";
        if (direct && direct.status < 400 && !ct.includes("text/html")) return direct;
        return new Response("Not Found", {
          status: 404,
          headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
        });
      }
      if (direct && direct.status < 400) {
        const ct = direct.headers.get("content-type") || "";
        // 只信任真正的静态资源；任何 HTML 一律交给 SPA 壳，避免 Pages 回退污染
        if (!ct.includes("text/html")) return direct;
      }
      const shell = await env.ASSETS.fetch(new Request(url.origin + "/app/index.html"));
      if (shell && shell.status < 400) {
        return new Response(shell.body, {
          status: 200,
          headers: { "content-type": "text/html; charset=utf-8" },
        });
      }
      return json(503, { success: false, message: "SPA 产物缺失：请先构建 frontend/ 并重新部署。" });
    }
    // 4. SEO 动态页前缀：静态 .html 优先、缺失再代理后端
    // 说明：Cloudflare Pages 对未命中的路径会做 SPA 回退（返回首页 index.html 且 status=200），
    // 直接 proxy 后端时后端也会对未知 slug 返回 SPA 壳，二者都会把我们的静态知识页顶替成首页。
    // 故改为：直接探测 path+.html 真实静态文件，命中且非 SPA 壳即返回；否则才代理后端动态页。
    if (path.startsWith("/knowledge/") || path.startsWith("/health/") || path.startsWith("/health-tools/")) {
      const candidates = (!path.endsWith(".html") && !path.endsWith("/")) ? [path + ".html"] : [path];
      for (const c of candidates) {
        const s = await env.ASSETS.fetch(new Request(url.origin + c));
        if (s && s.status < 400) {
          const txt = await s.text();
          // 命中 SPA 回退（首页标题含「您的健康全景平台」）→ 视为未命中，转代理后端
          if (txt.includes("您的健康全景平台")) continue;
          return new Response(txt, { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=3600" } });
        }
      }
      // 静态缺失 → 代理后端动态页（DB 长尾 SEO 页）
      try {
        const r = await proxy(request, env, url);
        if (r && r.status < 400) return r;
      } catch (e) { /* 后端不可用 */ }
      return new Response("Not Found", { status: 404 });
    }
    // 4b. sitemap.xml：优先取后端动态 sitemap（含全部 SEO 长尾页），失败或过小则回退静态
    if (path === "/sitemap.xml") {
      try {
        const r = await proxy(request, env, url);
        if (r && r.status === 200) {
          const body = await r.text();
          // 后端 sitemap 需显著多于静态版本才采用，避免后端异常导致收录量倒退
          if ((body.match(/<loc>/g) || []).length >= 50) {
            return new Response(body, {
              status: 200,
              headers: {
                "content-type": "application/xml; charset=utf-8",
                "cache-control": "public, max-age=3600",
              },
            });
          }
        }
      } catch (e) {
        /* 后端不可用时静默回退静态 sitemap */
      }
      const s = await serveStatic(request, env, url);
      if (s && s.status < 400) return s;
    }
    // 5b. humans.txt（人类可读 GEO 文件：ASSETS 兜底保障非空，避免边缘返回 0 字节）
    if (path === "/humans.txt") {
      const r = await serveStatic(request, env, url);
      if (r && r.status < 400) {
        const body = await r.text();
        if (body && body.trim().length) {
          return new Response(body, { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
        }
      }
      const today = new Date().toISOString().slice(0, 10);
      const fallback = `# humans.txt - HealthLens\n\n/* TEAM */\nSite: https://healthlens.cc\nMaintainer: HealthLens Team\nContact: https://healthlens.cc\n\n/* SITE */\nLanguage: zh-CN\nDoctype: HTML5\nBackend: FastAPI + PostgreSQL\nFrontend: Cloudflare Pages\nLast update: ${today}\n`;
      return new Response(fallback, { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    // 5. 其余（含 GEO 文件 sitemap.xml/llms.txt/ai.txt/robots.txt 与首页/静态资源）
    const assetResp = await serveStatic(request, env, url);
    if (assetResp && assetResp.status < 400) return assetResp;
    // SPA 回退：HTML 请求未命中静态资源时返回 index.html
    if ((request.headers.get("accept") || "").includes("text/html")) {
      return env.ASSETS.fetch(new Request(url.origin + "/index.html"));
    }
    return assetResp;
  },
};
