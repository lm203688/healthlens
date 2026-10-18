# HealthLens × Creem 支付接入 — 交接文档（2026-08-06）

> 状态：代码侧已全部完成并测试通过（185 passed）。**剩余步骤需你登录浏览器操作**（Cloudflare 环境变量 + Creem Dashboard webhook）。
> 商店：FrontierKB（`sto_7gBcCekvUKTpsaAFyf`）｜API Key：`creem_4yM8aDDK17QiHjWdiWgQEA`

---

## 一、我已经做完的（你不用动）

1. **验证 API Key + 4 个产品真实存在**（直连 `api.creem.io`）
   - `HealthLens Starter` / `Basic` / `Pro` / `Ultimate`（$1.99 / $5.99 / $17.99 / $39.99）均在 FrontierKB 商店，产品 ID 已对齐。
2. **修复产品映射键名**：前端 `buy.js` 传入 `hl_starter/hl_basic/hl_pro/hl_ultimate`，原映射只有 `starter/...`。已在 `creem_pay_service.py` 的 `CREEM_PRODUCT_MAP` 补齐 `hl_*` 键（并兼容旧键）。
3. **打通「发积分」闭环**（原缺口：webhook 只校验签名、不发放积分）：
   - `buy.js`：从 `Authorization: Bearer` 解析 JWT 取出 `user_id`，连同 `package_code` 写入 Creem checkout 的 `metadata`。
   - `payment.py` 的 `creem_webhook`：新增「路径B」——收到 `checkout.completed` 且本地无 `PointOrder` 时，按 `user_id`+`package_code` 直接发放积分（`CREEM_PACKAGE_POINTS`：hl_starter=100 / hl_basic=600 / hl_pro=2500 / hl_ultimate=6600），并做**幂等保护**（防 Creem 重试重复发分）。原有的「路径A（有 order_no）」逻辑保留。
   - 因此 webhook 应指向**后端** `/api/v1/payment/creem/webhook`（它能发积分），而不是边缘函数 `webhook.js`（那个只校验、不发放）。
4. **生成 webhook 签名密钥**并写入后端 `.env`（`.env` 已被 gitignore，不会进仓库）：
   - `CREEM_WEBHOOK_SECRET=a43b9a4ccc8f6db57dbeff1737f3a0076de51dd6ef39d1bc55196f1af1f25c50`
   - 同时写入 `CREEM_API_KEY` / `CREEM_API_BASE` / `CREEM_SUCCESS_URL` / `CREEM_WEBHOOK_URL`。
5. **回归测试**：新增 `tests/core/test_creem_pay.py`（4 项全过），全量 `pytest` 185 passed / 0 failed。

---

## 二、需要你操作的两件事

### 步骤 A：配置 Cloudflare Pages 环境变量（让线上购买链路能调 Creem）
链接：**https://dash.cloudflare.com** → 选中 HealthLens 的 Pages 项目 → **Settings → Environment variables**
（注意：如果生产域名走的是 Production 环境，变量要加在 **Production** 环境；预览用 Preview。）

请添加以下变量（名称＝值）：

| 变量名 | 值 |
|---|---|
| `CREEM_API_KEY` | `creem_4yM8aDDK17QiHjWdiWgQEA` |
| `CREEM_API_BASE` | `https://api.creem.io/v1` |
| `CREEM_PRODUCT_MAP` | `{"hl_starter":"prod_4ZW9DKv0fLeBMMSneWRhQZ","hl_basic":"prod_33tdtFuuezvwADrHGMFxgO","hl_pro":"prod_1aTggPK8Ebh5GXiJJ6wcE2","hl_ultimate":"prod_12gNTOtJv25lBU9qe1QQrf"}` |
| `CREEM_WEBHOOK_SECRET` | `a43b9a4ccc8f6db57dbeff1737f3a0076de51dd6ef39d1bc55196f1af1f25c50`（一致性用，边缘 webhook.js 用） |
| `SITE_URL` | `https://healthlens.cc`（如已是别的值可不动；buy.js 用它拼 success_url） |

> 改完环境变量后，**重新部署一次 Pages**（Environment variables 变更需重新发布才生效）。

### 步骤 B：在 Creem Dashboard 配置 Webhook（让支付成功事件回调后端发积分）
链接：**https://www.creem.io/dashboard** → 进入 FrontierKB 商店 → **Developers → Webhooks**（或 Settings → Webhooks）

1. **Add Endpoint**，填写：
   - **Webhook URL**：`https://healthlens.cc/api/v1/payment/creem/webhook`
     - ⚠️ 把 `healthlens.cc` 换成你**后端实际对外提供 `/api/v1` 的生产域名**（前端是同域部署，用哪个域名访问前端就用哪个）。
   - 勾选事件（至少）：`checkout.completed`（支付成功）、`refund.created`（退款）。
2. **Signing Secret（签名密钥）**：
   - 若 Creem 允许你**手动粘贴**密钥 → 粘贴这一串：`a43b9a4ccc8f6db57dbeff1737f3a0076de51dd6ef39d1bc55196f1af1f25c50`（与后端 `.env` 的 `CREEM_WEBHOOK_SECRET` 一致，后端才能验签通过）。
   - 若 Creem **自动生成**密钥 → 复制它发给我，我把后端 `.env` 的 `CREEM_WEBHOOK_SECRET` 改成这个值（否则验签会 401）。
3. 保存。

> 注意： Creem 的 webhook 是**商店级**配置，不在 checkout 请求里带 URL，所以只在 Dashboard 设一次即可。

---

## 三、需要你拍板的一个定价不一致（重要）

- 前端 `packages.js` 展示的是 **CNY**：体验包 ¥9.9 / 进阶包 ¥39 / 专业包 ¥128 / 旗舰包 ¥299。
- Creem 里你创建的产品是 **USD**：$1.99 / $5.99 / $17.99 / $39.99。

两者按 `package_code` 映射，但**用户看到的价格和实际扣款不一致**（例如看到 ¥9.9 却被扣 $1.99≈¥14）。请决定：
- **(推荐)** 改前端 `packages.js` 的 `price_cny` 字段为与 Creem 产品一致的金额/币种展示；或
- 在 Creem Dashboard 把产品定价改成你想要的 CNY 等价；或
- 保持现状但前端明确标注「美元计价」。

这个不影响发积分逻辑（积分按 `total_points` 发放），只影响用户感知，建议上线前对齐。

---

## 四、如何验证端到端（你配完 A/B 后）

1. 前端打开购买弹窗 → 选套餐 → 点「信用卡支付（Creem）」→ 应跳转到 Creem 收银台。
2. 用 Creem 提供的 **Test Mode / 测试卡** 完成支付（或在 Dashboard 手动标记测试订单）。
3. 回到站点，用该账号查积分余额，应**自动增加**对应套餐的积分（hl_starter=100 / hl_basic=600 / hl_pro=2500 / hl_ultimate=6600）。
4. 也可调管理接口自查：`GET /api/v1/payment/creem/setup-status`（需登录），返回 `all_ready=true` 即配置齐备。
5. 看后端日志应出现 `[CreemWebhook] Points credited via edge: user=..., pkg=hl_xxx, points=...`。

---

## 五、改动文件清单
- `app/services/creem_pay_service.py`（映射键对齐 + 积分映射 + webhook 解析 package_code）
- `app/api/payment.py`（webhook 双路径发积分 + 幂等）
- `frontend/functions/api/v1/growth/points/buy.js`（解析 user_id 写入 metadata）
- `.env`（新增 Creem 变量，**不入库**）
- `tests/core/test_creem_pay.py`（新增回归测试）

> ⚠️ 安全提醒：`.env` 含密钥，**切勿 `git add .env`**。inner 仓库 `origin` 仍含明文 GitHub PAT，请尽快轮换吊销。
