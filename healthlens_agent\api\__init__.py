"""healthlens_agent 控制面 API 模块（**未挂载**，勿直接 include_router）。

这些模块原本散落在 `app/api/` 下，但与 `app/api/` 中已注册的 41 个公开路由
无关 —— 它们是 `healthlens_agent/` 控制面（自动化管线 / 技能注册表 / 合规同意 /
报告生成）的 HTTP 包装，且通过文件路径加载 `healthlens_agent/*.py`。
2026-09-23 收敛：从 `app/api/` 迁到此处，使其与所依赖的代码同处一地，
消除「`app/api/` 有文件但线上没有路由」的持续误判。

当前状态与挂载前置条件（**任一不满足都不得挂载**）
---------------------------------------------------
1. **鉴权**：4 个模块的所有端点都没有 `Depends(get_current_user)`。
   `POST /skills/{name}/run` 可执行任意已注册技能、`POST /pipeline/phase/{id}/run`
   可触发内容管线、`GET /compliance/consent/{user_id}` 可读他人同意记录 ——
   直接挂载等于把内部运维面暴露到公网。挂载前必须加 admin 依赖。
2. **代码可达**：这些模块按 `Path(__file__).parent.parent.parent` 推算仓库根，
   再去读 `healthlens_agent/*.py`。而 web 容器只 bind mount 了 `./app` 与
   `./data`，`healthlens_agent/` 与 `auto-pipeline/` 都不在容器内 ——
   即使挂载成功也会在首次调用时 ImportError。
3. **存储**：`compliance_api` 的同意记录写本地文件（`CONSENT_DIR`），容器内
   为临时层，重启即失、多副本不共享。要作为真实合规面（GDPR/CCPA 同意留痕），
   须先改为写数据库表。

结论：这 4 个模块目前是**未接线的控制面草稿**。要么补齐上述三项后以
`/api/v1/admin/*` 正式挂载，要么删除。不要为了让路由数好看而挂上去。
"""
