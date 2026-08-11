// HealthLens 创建支付订单（Cloudflare Pages Function）
// 前端调用：/api/v1/growth/points/buy?package_code=XX&payment_method=YY
//
// 支持的支付方式（全部转发到后端 FastAPI 源站创建订单）：
//   - xunhu / wechat / alipay  国内虎皮椒，CNY，返回 pay_url / qrcode_url
//   - creem                    国际信用卡，USD，返回 checkout_url
//     Creem 使用 HealthLens 专属店铺，与其他业务店铺完全隔离（后端强制校验 store_id）。
//
// 环境变量（Cloudflare Pages 项目 Settings > Environment variables）：
//   BACKEND_URL  后端 FastAPI 源站地址（如 https://api.healthlens.cc 或 http://<server-ip>:8000）
//               【必填】切勿填 Cloudflare Pages 域名（会回环调用本函数导致死循环）。
//   SITE_URL    https://healthlens.cc（可选）

const SUPPORTED_METHODS = ["xunhu", "wechat", "alipay", "creem", "card", "international", "mock"];

function base64UrlDecode(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 ? 4 - (s.length % 4) : 0;
  s += "=".repeat(pad);
  return atob(s);
}

export async function onRequestPost(context) {
  const url = new URL(context.request.url);
  const method = (url.searchParams.get("payment_method") || "xunhu").toLowerCase();
  const env = context.env || {};

  if (!SUPPORTED_METHODS.includes(method)) {
    return Response.json(
      {
        success: false,
        message: "不支持的支付方式。国内请使用微信/支付宝，海外请使用信用卡（creem）。",
      },
      { status: 400 }
    );
  }

  // 从 Authorization: Bearer <jwt> 解析 user_id，仅用于日志定位；订单归属以后端 JWT 校验为准
  let userId = "";
  const auth = context.request.headers.get("Authorization") || "";
  const am = auth.match(/^Bearer\s+(.+)$/i);
  if (am) {
    try {
      const payload = JSON.parse(base64UrlDecode(am[1].split(".")[1] || ""));
      userId = String(payload.sub || payload.user_id || payload.id || "");
    } catch (e) {
      userId = "";
    }
  }
  if (!auth) {
    return Response.json(
      { success: false, message: "请先登录后再购买。" },
      { status: 401 }
    );
  }

  const backend = env.BACKEND_URL;
  if (!backend) {
    return Response.json(
      {
        success: false,
        message: "支付通道未配置：请在 Cloudflare 环境变量设置 BACKEND_URL（后端源站地址）。",
      },
      { status: 503 }
    );
  }

  const target =
    backend.replace(/\/$/, "") + "/api/v1/growth/points/buy?" + url.searchParams.toString();

  try {
    const fwd = await fetch(target, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
    });
    const text = await fwd.text();
    return new Response(text, {
      status: fwd.status,
      headers: { "content-type": fwd.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return Response.json(
      { success: false, message: "转发后端失败：" + e.message },
      { status: 502 }
    );
  }
}
