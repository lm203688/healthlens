// GEO 文件代理：/humans.txt -> 后端 FastAPI（项目信息）
import { proxy } from "./_proxy.js";
export const onRequest = proxy;
