// HealthLens 支付 Webhook（Cloudflare Pages Function）
// Creem 在支付成功/失败时回调此地址，验证签名后返回 200 即可。
// 配置：Cloudflare Pages 项目 Settings > Environment variables 设置 CREEM_WEBHOOK_SECRET；
//       并在 Creem Dashboard > Developers > Webhooks 填入本地址：
//       https://healthlens.cc/api/v1/growth/points/webhook
//
// 说明：当前为静态站，未接用户账户库。Webhook 仅做「签名校验 + 落库(可选 KV)」，
//       真正给用户「发放积分」需后端账户系统（app/ 服务）上线后在此扩展。
//       付款本身已真实发生，Creem 后台可见订单与对账。

async function hmacSha256(secret, raw) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(raw));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequestPost(context) {
  const env = context.env || {};
  const secret = env.CREEM_WEBHOOK_SECRET;
  const sig = context.request.headers.get("creem-signature");
  const raw = await context.request.text();

  if (secret && sig) {
    const calc = await hmacSha256(secret, raw);
    if (calc !== sig) {
      return new Response("invalid signature", { status: 401 });
    }
  }

  // 可选：若有 KV 绑定 ORDERS，则持久化事件用于后续对账/发放积分
  try {
    if (env.ORDERS) {
      const evt = JSON.parse(raw || "{}");
      const id = (evt && evt.id) || ("evt_" + Date.now());
      await env.ORDERS.put(id, raw);
    }
  } catch (e) { /* 不阻塞 webhook 响应 */ }

  return new Response("ok", { status: 200 });
}
