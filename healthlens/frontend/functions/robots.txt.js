// GEO 文件代理：/robots.txt -> 后端 FastAPI
import { proxy } from "./_proxy.js";
export const onRequest = proxy;
