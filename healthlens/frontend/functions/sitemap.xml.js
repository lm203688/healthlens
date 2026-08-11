// GEO 文件代理：/sitemap.xml -> 后端 FastAPI（动态 sitemap）
import { proxy } from "./_proxy.js";
export const onRequest = proxy;
