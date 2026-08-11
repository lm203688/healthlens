// 健康工具页代理：/health-tools/* -> 后端 FastAPI
// 覆盖 SEO 落地页（/health-tools/<slug>）与实际工具页（/health-tools/tools/<slug>），
// 二者均由后端同一组 router 提供，因此统一代理。
import { proxy } from "../_proxy.js";
export const onRequest = proxy;
