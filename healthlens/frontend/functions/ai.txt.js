// GEO 文件代理：/ai.txt -> 后端 FastAPI（AI 可读摘要）
import { proxy } from "./_proxy.js";
export const onRequest = proxy;
