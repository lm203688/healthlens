# HealthLens 敏感数据流图与整改（P1-SEC-01）

> 工作单：`P1-SEC-01`（报告《HealthLens 全面提升方案 2026-10-27》附录 A 第 7 项）
> 日期：2026-10-27 · 范围：token、聊天、缓存、分享、日志五类敏感数据流
> 定位：wellness 平台（非医疗）。本图是**降低泄露面**的护栏，不是渗透测试结论。

---

## 1. 数据流总览（五类）

```text
                         ┌─────────────────────────────┐
                         │   前端浏览器 (SPA)           │
                         │  localStorage / sessionStorage│
                         └──────┬──────────┬───────────┘
                                │          │
                 ① token 签发    │          │ ③ 聊天持久化
                         ┌──────▼──┐   ┌───▼────────┐
                         │ auth.py │   │ chatStore  │
                         │ 签发JWT │   │ (localSt.) │
                         └──────┬──┘   └───┬────────┘
                                │          │
                 Bearer 头 → deps.get_current_user
                                │
   ┌──────────────┬─────────────┼──────────────┬───────────────┐
   │              │             │              │               │
   ▼              ▼             ▼              ▼               ▼
 ② Agent 端点  ④ 分享         ⑤ Redis 缓存   ⑥ 日志落盘       (其余业务端点)
 agent.py      share_report  device_metrics  logging_config  均已带鉴权
 pulse.py      share_public  edge_ticket     loguru 文件
 (+/agent/pulse)              (+ops_tasks)
```

---

## 2. 逐类盘点与整改

### ① Token 签发与存储

| 环节 | 位置 | 现状 | 整改 |
|---|---|---|---|
| 签发 | `app/utils/security.py` | `create_access_token` / `create_refresh_token`（JWT，`sub`=user_id，`type`=access/refresh） | 无需改（已带 `type` 区分，`decode_token` 校验 `type=="access"`） |
| 校验 | `app/api/deps.py` | `get_current_user`：HTTPBearer + `decode_token`，校验 type + sub 存在 | 无需改 |
| 前端存储 | `frontend/src/App.jsx` | `localStorage` 存 `token`/`refresh_token`/`user_email` | **已知残余风险**：localStorage 可被 XSS 读取。SPA 无 httpOnly cookie 条件下的最小可行方案；已在文档标注，未本轮强改（改动面大，属独立工作单） |
| 前端请求 | `frontend/src/api/client.js` | `request`/`requestForm`/`requestStream` 统一附 Bearer + 401 跳转（P0-AUTH-01） | 无需改 |

### ② Agent 端点鉴权（本轮整改重点）

**整改前**：`app/api/agent.py` 的 `/fusion`、`/team`、`/team/stream` 与 `app/api/pulse.py` 的 `/agent/pulse` **无鉴权依赖**——任何匿名请求可调用 LLM 团队管线与按 `user_ref` 拉取号脉数据。

**整改后**：四端点均加 `current_user: User = Depends(get_current_user)`，并传入 `apply_claims(user=current_user)`（法域感知，替代此前硬编码 `jurisdiction="cn"`）。

| 端点 | 整改前 | 整改后 |
|---|---|---|
| `POST /api/v1/agent/fusion` | 匿名可达，`apply_claims(..., None, "cn")` | 需登录，`apply_claims(..., user)` |
| `POST /api/v1/agent/team` | 匿名可达，`apply_claims(..., None, "cn")` | 需登录，`apply_claims(..., user)` |
| `POST /api/v1/agent/team/stream`（SSE） | 匿名可达 | 需登录（依赖在流式响应前解析） |
| `POST /api/v1/agent/pulse` | 匿名可达（按 user_ref 拉数据） | 需登录 |

前端调用侧核对：`client.js` 的 `agentFusion`/`agentTeam`/`agentTeamStream` 均走统一 `request`/`requestStream`（附 Bearer），调用页面（Dashboard / HealthAssess / MyChanges / Onboarding / AgentChat）均在 `<RequireAuth>` 路由守卫内——**加鉴权不破坏现有前端流程**。

### ③ 聊天持久化

| 环节 | 位置 | 现状 | 整改 |
|---|---|---|---|
| 前端存储 | `frontend/src/lib/chatStore.js` | `localStorage` `hl_chat_history_v1`，会话上限 10、每会话 100 条、加载窗口 50、上下文窗口 6 | **已知残余风险**：聊天内容（可能含健康信息）明文落 localStorage。已设容量上限与清空入口；加密存储需密钥管理，属独立工作单 |
| 后端入口 | `app/api/agent.py` | 本轮已加鉴权；SSE 端点 `finally` 复位（P0-FE-03） | 已完成 |

### ④ 分享

| 环节 | 位置 | 现状 | 整改 |
|---|---|---|---|
| Token 生成 | `app/services/share_report_service.py` | `secrets.token_urlsafe(24)[:32]`（192-bit 熵） | 无需改（熵足够） |
| Token 入日志 | 同文件 `logger.info` | **此前完整 token 明文打日志** | **已改**：只打 `token[:6]...` 前缀 |
| 访问控制 | `app/api/share_public.py` | `get_shared_report`：校验 `is_public` + `expires_at` | 无需改（已校验） |
| 授权/撤销 | `app/api/share_report.py` | `expires_days`（0=永不过期）、`revoke_report`（按 user_id 归属） | 无需改（已按用户归属） |

### ⑤ 缓存（Redis）

| 环节 | 位置 | 现状 | 整改 |
|---|---|---|---|
| Key 构造 | `app/api/device_metrics.py` | `METRIC_KEY="hl:edge:metrics:{user_ref}:{day}"`，`REF_PATTERN` 限定字符集防越权前缀扫描；TTL 30 天 | 无需改（已隔离） |
| 失效清单 | `app/api/edge_ticket.py` | `jti` 进 Redis 失效清单，接收口每次查询 | 无需改 |
| 业务缓存 | `app/tasks/ops_tasks.py` | 仅 ops 任务使用，无用户 PII 键 | 无需改 |
| 存储内容 | `device_metrics` | 日粒度指标（非原始波形），TTL 自动过期 | 无需改（原始波形默认本地处理，见 §5.3） |

### ⑥ 日志（本轮整改重点）

**整改前**：`app/utils/logging_config.py` 用 loguru 写 `logs/healthlens_*.log`，**无 PII 脱敏**——token / email / 手机号 / 身份证等以明文落盘。

**整改后**：新增 `_pii_sanitizing_filter`，两个 sink（stderr + 文件）均挂载，写入前经 `pii_sanitizer.sanitize(use_presidio=False, strict=True)`：

```python
def _pii_sanitizing_filter(record) -> bool:
    msg = record.get("message")
    if isinstance(msg, str) and msg:
        try:
            record["message"] = sanitize(msg, use_presidio=False, strict=True)
        except Exception:
            pass  # 脱敏失败不阻断日志管道
    return True
```

- `strict=True`：用校验位过滤（身份证/银行卡），少误报——日志是落盘点，宁可漏掉畸形号码也不要误伤订单号。
- `use_presidio=False`：生产未装 Presidio，显式关闭避免每次日志都尝试加载 NER。
- 审计落库路径 `app/services/runtime_audit.py` 已先脱敏（`persist_events`），本 filter 补齐**文件日志**侧。

---

## 3. 整改汇总

| # | 整改项 | 文件 | 类型 |
|---|---|---|---|
| 1 | 日志 PII 脱敏 filter（两 sink） | `app/utils/logging_config.py` | 修复 |
| 2 | 分享 token 只打前缀 | `app/services/share_report_service.py` | 修复 |
| 3 | agent `/fusion` `/team` `/team/stream` 加鉴权 + 法域感知 | `app/api/agent.py` | 修复 |
| 4 | `/agent/pulse` 加鉴权 | `app/api/pulse.py` | 修复 |
| 5 | 回归测试（11 用例） | `tests/core/test_security_dataflow.py` | 新增 |

## 4. 已知残余风险（诚实声明，未在本轮强改）

1. **前端 localStorage**：token / 聊天历史 / user_email 明文，XSS 可读。SPA 无 httpOnly cookie 时的最小可行方案；升级到 httpOnly + CSRF 或 Web Crypto 加密存储需独立工作单。
2. **中文人名 NER**：规则层对中文人名无能为力（生产未装 Presidio），日志脱敏覆盖不到人名类实体。`pii_sanitizer.backend_info()` 返回 `presidio_available` 真值供巡检。
3. **分享报告内容**：`report_data` JSON 快照本身含健康摘要，公开访问凭 `share_token`（高熵）。已设过期与撤销，但 token 一旦泄露即需撤销——前端应提供"一键撤销"入口（已有 `revoke_report`）。

## 5. 测试

`tests/core/test_security_dataflow.py`（11 用例）覆盖：
- 日志 filter：手机号/邮箱/身份证掩码、幂等、非字符串不崩、恒返回 True（不吞日志）
- agent 四端点未带 token → 401
- 分享 token 日志不含完整 token
