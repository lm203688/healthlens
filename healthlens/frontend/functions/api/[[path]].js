// HealthLens API 全量反向代理（Cloudflare Pages Function）
//
// 作用：把 Pages 域名下的 /api/** 请求原样转发到后端 FastAPI 源站。
// 这解决了「前端部署在 Pages、后端在别处」时所有后端接口 404 的根本问题，
// 包括但不限于：注册登录、诊断 agent-run、积分、以及**支付异步回调**
//   - 虎皮椒 /api/v1/payment/notify
//   - Creem   /api/v1/payment/creem/webhook
// 回调打不通 = 用户付了钱不到账，因此这条链路必须可达。
//
// 说明：
//  - 更具体的 Function（如 points/buy.js、points/packages.js）优先级高于本 catch-all，
//    它们会先被匹配，本文件只兜住其余路径。
//  - 转发保留原始 method / headers / query / body（原始字节），
//    否则 Creem 与虎皮椒的签名校验会失败。
//  - 共享逻辑见 ../_proxy.js，本文件仅做转发，避免多处实现分叉。

import { proxy } from "../_proxy.js";
export const onRequest = proxy;
