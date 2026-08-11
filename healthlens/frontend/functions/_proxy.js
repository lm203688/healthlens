// 共享反向代理逻辑（Cloudflare Pages Function）
//
// 把 Pages 域名下的指定路径原样转发到后端 FastAPI 源站。
// 用于 SEO 公开页（/knowledge/、/health/、/health-tools/）与 GEO 文件
// （/sitemap.xml、/robots.txt、/llms.txt、/ai.txt、/humans.txt），
// 这些路径不在 /api/ 下，因此 functions/api/[[path]].js 兜不到，必须单独代理。
//
// 转发保留原始 method / headers / query / body（原始字节），
// 否则 Creem 与虎皮椒的签名校验会失败。
//
// 环境变量：
//   BACKEND_URL  后端源站地址，例如 https://api.healthlens.cc
//                【必填】不能是本 Pages 站自身域名，否则会无限回环。

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "host",
  "content-length",
]);

async function proxy(context) {
  const env = context.env || {};
  const reqUrl = new URL(context.request.url);
  const backend = env.BACKEND_URL;

  if (!backend) {
    return Response.json(
      {
        success: false,
        message:
          "后端未配置：请在 Cloudflare Pages 环境变量中设置 BACKEND_URL 指向 FastAPI 源站。",
      },
      { status: 503 }
    );
  }

  let backendUrl;
  try {
    backendUrl = new URL(backend);
  } catch (e) {
    return Response.json(
      { success: false, message: "BACKEND_URL 不是合法的 URL。" },
      { status: 503 }
    );
  }

  // 防回环：BACKEND_URL 指向自己会导致无限递归
  if (backendUrl.host === reqUrl.host) {
    return Response.json(
      {
        success: false,
        message: "BACKEND_URL 不能指向本站域名（会造成回环）。请填写后端源站地址。",
      },
      { status: 503 }
    );
  }

  const target =
    backendUrl.origin + reqUrl.pathname + (reqUrl.search || "");

  // 复制请求头，去掉 hop-by-hop 与 host
  const headers = new Headers();
  for (const [k, v] of context.request.headers) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set("X-Forwarded-Host", reqUrl.host);
  headers.set("X-Forwarded-Proto", reqUrl.protocol.replace(":", ""));

  const method = context.request.method.toUpperCase();
  const init = { method, headers, redirect: "manual" };

  // 保留原始字节，签名校验依赖未经改动的 body
  if (!["GET", "HEAD"].includes(method)) {
    init.body = await context.request.arrayBuffer();
  }

  try {
    const resp = await fetch(target, init);
    const respHeaders = new Headers();
    for (const [k, v] of resp.headers) {
      if (!HOP_BY_HOP.has(k.toLowerCase())) respHeaders.set(k, v);
    }
    return new Response(resp.body, { status: resp.status, headers: respHeaders });
  } catch (e) {
    return Response.json(
      { success: false, message: "后端不可达：" + e.message },
      { status: 502 }
    );
  }
}

export { proxy };
