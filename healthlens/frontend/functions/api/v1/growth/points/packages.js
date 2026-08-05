// HealthLens 套餐列表（Cloudflare Pages Function）
// 前端 buy-points 弹窗直接读取此接口，无需后端。
export async function onRequestGet(context) {
  const packages = [
    {
      package_code: "hl_starter",
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
      package_code: "hl_basic",
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
      package_code: "hl_pro",
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
      package_code: "hl_ultimate",
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
  return Response.json({ success: true, data: packages });
}
