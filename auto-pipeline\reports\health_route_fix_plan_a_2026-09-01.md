# HealthLens 后端连通性缺口 — 方案 A 执行清单（**已升级为站点级**）

> 状态：**已 100% 锁定根因，且已验证影响范围 = 站点级后端中断，不止 `/health` 监控缺口。修复仅需用户在 Cloudflare 控制台放宽 `api.healthlens.cc` 边缘规则，无需重部署。**
> 方案 A = 放宽 `api.healthlens.cc` zone 的边缘规则，放行全部后端路径（`/api/**`、`/health`、`/metrics`）。

---

## 〇、2026-09-01 实测复核结论（本次「continue」新增，已闭环）

**调用链**：`healthlens.cc`(Worker) → `api.healthlens.cc`(CF 边缘) → `150.158.119.19`(nginx) → `127.0.0.1:8000`(FastAPI)

| 探测点 | 结果 | 含义 |
|---|---|---|
| ECS `127.0.0.1:8000/health`（SSH 直连，早前验证） | `200 {"status":"ok","version":"0.18.1"}` | 后端进程健康、无 Host 限制 ✅ |
| 线上 `healthlens.cc/health`（worker 合成态） | `200 {"status":"degraded","backend_reachable":false}` | worker 已诚实返回，但探测后端失败 ⚠️ |
| 线上 `healthlens.cc/api/v1/growth/points/packages` | `200` 但 body 含 `"source":"edge-fallback"` | **worker 拿不到真后端，回退静态套餐** ❌ |
| 线上 `healthlens.cc/api/openapi.json`、`/api/v1/health`、`/api/v1/growth/points/balance` | `404`（空 body，**非 502**） | `proxy()` 未抛错 → 子请求抵达 CF 边缘被 404，源站根本没收到 ❌ |
| 访客直连 `api.healthlens.cc/`、`/api/...`、`/health` | **全部 `404`**（Server: cloudflare） | **`api.healthlens.cc` 边缘对所有路径返回 404** ❌ |

**关键推论（已用两条独立证据闭环）**：
1. `proxy()` 仅在 `fetch` 抛异常时返回 `502`；实测 `/api/openapi.json` 等返回 **404 空体** → 说明子请求**成功发出但被 `api.healthlens.cc` 边缘 404**，源站从未收到。
2. 访客直连 `api.healthlens.cc` 任意路径同样 404 → 与 worker 子请求行为一致，说明这是**同一个 zone 边缘规则在拦截一切**。

**最终定性**：`api.healthlens.cc` 的 Cloudflare 边缘规则（WAF/Custom Rule 或 Origin Rule）当前对**所有入站路径返回 404**（不是「仅放行 `/api`」）。后果：
- 访客经 `api.healthlens.cc` 全部 404；
- Worker 经 `resolveOverride` 的子请求也走同一 zone 边缘 → 同样 404 → **整条 `/api` 通道失效**：套餐接口退回静态兜底、其余接口 404 空体。
- 即：**线上所有依赖后端的动态功能（套餐/支付/账户/报告）当前拿不到真实数据**。这是站点级后端中断，不是 `/health` 监控小缺口。

> 注：早期（03:04/03:30）的「live-check ok」「/api 返回 200」均为**仅看状态码**的检查——套餐接口 200 是因为 worker 回退了静态数据、其余接口当时未被内容校验，故把故障掩盖了。本次用 `source` 标签 + 空体 404 才暴露。

---

## 一、AI 侧已完成（你无需重复）

- `healthlens/frontend/_worker.js` 第 184 行 `/health` 诚实健康态已部署：后端不可达时返回 `200 {"status":"degraded","backend_reachable":false}`，并附 `note` 指引修复；若边缘日后放行，会自动直出真后端 `{"status":"ok"}`。
- 三处 worker 源（源文件 / `.workbuddy/cache/deploy_out/_worker.js` / `auto-pipeline/dist/_worker.js`）均已含该规则且内容一致 → 小时级部署不会静默回退。
- 三条 `cfut_*` 令牌均为 Pages-only，**无 Zone/Firewall 写权** → 控制台改规则必须手动。

---

## 二、方案 A 手动步骤（Cloudflare 控制台，影响全后端）

1. 登录 Cloudflare（账户 `61960005@qq.com`，Account ID `8162aa3b2241c132e43a81f526d7f758`）。
2. 进入站点 **`api.healthlens.cc`**（注意是 `api.` 子域这个 zone，不是 `healthlens.cc`）。
3. 找到那条「对所有路径返回 404」的规则，按优先级排查：
   - **Security → WAF → Custom Rules**（最可疑；旧版叫 Firewall → Firewall Rules）
   - **Security → WAF → Rate Limiting Rules**
   - **Rules → Transform / Cache / Page Rules**
   - **Zero Trust → Access → Applications**（若启了 Access，未认证访问会被拒）
   - 也检查 **SSL/TLS → Origin Server** 与 DNS 记录：确认 `api.healthlens.cc` 的 A/AAAA 记录指向 `150.158.119.19` 且为「代理(橙云)」状态；若记录缺失/指向错误也会整体 404。
4. 修复二选一：
   - **方式一（加 Allow 例外，推荐）**：新建高优先级规则
     - 表达式：`(http.request.uri.path matches "^/api/") or (http.request.uri.path eq "/health") or (http.request.uri.path eq "/metrics")`
     - 动作：**Allow**（或 **Skip**，跳过剩余 WAF 规则）
     - 放到那条「拦截」规则**上方**
   - **方式二（改原规则）**：把原「拦截全部」表达式改为只拦截真正的非法路径，放行 `^/api/`、`/health`、`/metrics`。
5. 保存。**边缘秒级生效，无需任何部署动作。**

---

## 三、验证（改完即测，含后端真实性校验）

```bash
# 1) /health 应脱离 degraded，返回真实 ok
curl -s https://healthlens.cc/health
# 期望：{"status":"ok","version":"0.18.1",...}  （backend_reachable 不再为 false）

# 2) /api 必须返回「非兜底」真实数据（关键！）
curl -s https://healthlens.cc/api/v1/growth/points/packages | grep -c '"source":"edge-fallback"'
# 期望：0  （若仍为 1，说明后端路径仍被边缘拦截，未修好）

# 3) 其它 /api 端点必须不再是 404 空体
curl -s -o /dev/null -w '%{http_code}\n' https://healthlens.cc/api/openapi.json
# 期望：200
```

改完把三步结果贴给我，我帮你做最终回读确认（含 `/metrics` 一并核验）。

---

## 四、备选（不碰 Cloudflare，但治标不治本）

若改边缘规则不方便，可改 worker 让 `/api` 也走「合成」通道——但这**只能让监控看起来正常，无法恢复真实后端数据**（因为根因是边缘拦掉了到源站的所有路径）。**真正恢复业务必须走方案 A**。备选仅建议在方案 A 暂不能做时用于「不让监控长期误报 degraded」。
