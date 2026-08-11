// GEO 文件代理：/llms.txt -> 后端 FastAPI（AI 引擎指令文件）
import { proxy } from "./_proxy.js";
export const onRequest = proxy;
