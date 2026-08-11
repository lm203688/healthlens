// SEO 健康话题页代理：/health/* -> 后端 FastAPI（SeoPage 渲染）
import { proxy } from "../_proxy.js";
export const onRequest = proxy;
