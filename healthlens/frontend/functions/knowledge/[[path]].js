// SEO 知识页代理：/knowledge/* -> 后端 FastAPI（SeoPage 渲染）
import { proxy } from "../_proxy.js";
export const onRequest = proxy;
