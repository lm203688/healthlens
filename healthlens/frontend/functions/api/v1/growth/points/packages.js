// HealthLens 套餐列表（Cloudflare Pages Function）
//
// 单一事实来源 = 后端 FastAPI 的 /api/v1/growth/points/packages。
// 本函数只做转发，避免边缘与后端出现两套 package_code（历史上边缘用 hl_*、
// 后端用 starter/basic/pro/ultimate，任何误用都会让下单接口返回「套餐不存在」）。
//
// 当 BACKEND_URL 未配置或后端不可达时，回退到与后端**完全一致**的静态兜底数据，
// 保证购买弹窗不至于空白（package_code 必须与后端一致才能成功下单）。
//
// 环境变量：BACKEND_URL —— 后端源站地址，切勿填 Pages 域名（会回环）。

const FALLBACK_PACKAGES = [
  {
    package_code: "starter",
    package_name: "体验包",
    price_cny: 9.9,
    points_amount: 100,
    total_points: 100,
    is_popular: false,
    description: "1 次完整报告解析（五层因果链 + 基础食养方案）",
    bonus_points: 0,
    original_price: 0,
  },
  {
    package_code: "basic",
    package_name: "进阶包",
    price_cny: 39,
    points_amount: 550,
    total_points: 600,
    is_popular: true,
    description: "5 次解析 + 风险分层 + 频率修复 + 方案反馈",
    bonus_points: 50,
    original_price: 49,
  },
  {
    package_code: "pro",
    package_name: "专业包",
    price_cny: 128,
    points_amount: 2300,
    total_points: 2500,
    is_popular: false,
    description: "23 次深度基因代谢解读 + 顾问优先响应",
    bonus_points: 200,
    original_price: 158,
  },
  {
    package_code: "ultimate",
    package_name: "旗舰包",
    price_cny: 299,
    points_amount: 6000,
    total_points: 6600,
    is_popular: false,
    description: "60 次解析 + 家庭共享(3人) + 全年健康档案",
    bonus_points: 600,
    original_price: 399,
  },
];

export async function onRequestGet(context) {
  const env = context.env || {};
  const backend = env.BACKEND_URL;

  if (backend) {
    try {
      const fwd = await fetch(
        backend.replace(/\/$/, "") + "/api/v1/growth/points/packages",
        { headers: { "Content-Type": "application/json" } }
      );
      if (fwd.ok) {
        const text = await fwd.text();
        return new Response(text, {
          status: fwd.status,
          headers: {
            "content-type": fwd.headers.get("content-type") || "application/json",
            "cache-control": "public, max-age=60",
          },
        });
      }
    } catch (e) {
      // 落到静态兜底
    }
  }

  return Response.json(
    { success: true, data: FALLBACK_PACKAGES, source: "edge-fallback" },
    { headers: { "cache-control": "public, max-age=60" } }
  );
}
