// HealthLens 创建支付订单（Cloudflare Pages Function）
// 前端 buy-points 流程调用：/api/v1/growth/points/buy?package_code=XX&payment_method=creem
// 真实调用 Creem 创建托管结账，返回 checkout_url 由前端跳转。
//
// 环境变量（在 Cloudflare Pages 项目 Settings > Environment variables 配置）：
//   CREEM_API_KEY        Creem API Key（x-api-key 使用）
//   CREEM_API_BASE       https://api.creem.io/v1 或 https://test-api.creem.io/v1
//   CREEM_PRODUCT_MAP    JSON: {"hl_starter":"prod_xxx", ...} 各套餐对应的 Creem 产品ID
//   CREEM_WEBHOOK_SECRET Creem Webhook 签名密钥（用于 /webhook 校验）
//   SITE_URL             https://healthlens.cc

function safeJson(s, fallback) {
  try { return JSON.parse(s); } catch (e) { return fallback; }
}

async function fetchProducts(apiBase, apiKey) {
  try {
    const r = await fetch(apiBase + "/products", { headers: { "x-api-key": apiKey } });
    if (!r.ok) return [];
    const d = await r.json();
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d.items)) return d.items;
    if (d && Array.isArray(d.data)) return d.data;
    return [];
  } catch (e) { return []; }
}

export async function onRequestPost(context) {
  const url = new URL(context.request.url);
  const packageCode = url.searchParams.get("package_code") || "";
  const method = (url.searchParams.get("payment_method") || "creem").toLowerCase();
  const env = context.env || {};

  if (method !== "creem") {
    return Response.json(
      { success: false, message: "微信/支付宝通道即将上线，请先选择「信用卡支付（Creem）」完成下单。" },
      { status: 200 }
    );
  }

  const apiKey = env.CREEM_API_KEY;
  const apiBase = env.CREEM_API_BASE || "https://api.creem.io/v1";
  if (!apiKey) {
    return Response.json({ success: false, message: "支付未配置：缺少 CREEM_API_KEY" }, { status: 200 });
  }

  // 1) 解析 Creem 产品 ID
  let productId = null;
  const map = env.CREEM_PRODUCT_MAP ? safeJson(env.CREEM_PRODUCT_MAP, null) : null;
  if (map && map[packageCode]) productId = map[packageCode];
  if (!productId) {
    const list = await fetchProducts(apiBase, apiKey);
    const found = list.find((p) => p.code === packageCode);
    productId = found ? (found.id || found.product_id) : null;
  }
  if (!productId) {
    return Response.json({ success: false, message: "未找到对应 Creem 产品：" + packageCode }, { status: 200 });
  }

  // 2) 创建托管结账
  const successUrl = (env.SITE_URL || "https://healthlens.cc") + "/#buy-success";
  const body = {
    product_id: productId,
    success_url: successUrl,
    metadata: { package_code: packageCode, source: "healthlens_site" },
  };
  let data = {};
  try {
    const resp = await fetch(apiBase + "/checkouts", {
      method: "POST",
      headers: { "x-api-key": apiKey, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.checkout_url) {
      return Response.json(
        { success: false, message: "创建支付失败：" + (data.message || resp.status) },
        { status: 200 }
      );
    }
  } catch (e) {
    return Response.json({ success: false, message: "调用 Creem 出错：" + e.message }, { status: 200 });
  }

  const orderNo = (data.order && (data.order.id || data.order.order_id)) || data.id || "ord_" + Date.now();
  return Response.json({ success: true, data: { checkout_url: data.checkout_url, order_no: orderNo } });
}
