# M09 报告生成与合规 Claims 输出 — 板块独立评估报告

> 评估日期：2026-10-14 ｜ 方法：代码级实测 + 监管/竞品/开源检索

---

## 一、板块定位与代码归属

| 项 | 内容 |
|---|---|
| 合规核心 | `app/lib/claims_engine.py`（456 行 / 12 函数 / 2 类） |
| 策略 | `claims_policy/`：`cn.yaml`(PIPL+NMPA)、`us_fda.yaml`、`uk_mhra.yaml`、`au_tga.yaml`、`eu_mdr.yaml` |
| 报告 | `app/api/reports.py`、`share_report.py`、`share_public.py` |
| 服务 | `app/services/share_report_service.py` |
| 前端 | `frontend/src/pages/Reports.jsx`、`Share.jsx` |

**引擎五项职责**（代码注释原话）：
1. `load_policy(jurisdiction)` 加载 YAML（首次后缓存）
2. `filter_output(payload, jurisdiction)` 字段级过滤/改写/拦截
3. `check_endpoint_allowed(endpoint, jurisdiction)` 端点级开关
4. `scan_terms(text, jurisdiction)` 敏感词扫描
5. `apply_disclaimer(payload, context, jurisdiction)` 按法域定制免责声明

**关键设计约束**：每次过滤留痕审计（`AuditEvent.severity=medium`）；**未配置策略 → 默认走最严格（EU）而非放行（fail-closed）**；未知 jurisdiction 直接抛 `ClaimsPolicyError`。

---

## 二、流程走通性实测

**主链路**：生成报告 → `apply_filter()` → 审计留痕 → 分享

| 环节 | 状态 | 判据 |
|---|---|---|
| 5 法域加载 | ✅ 实测通过 | `SUPPORTED_JURISDICTIONS = {'au', 'us', 'cn', 'uk', 'eu'}` |
| fail-closed | ✅ 好 | 未知法域 → 最严格 EU 策略，不静默放行 |
| 端点级开关 | ✅ 存在 | `check_endpoint_allowed()` |
| 敏感词扫描 | ✅ 存在 | `scan_terms()` |
| 审计留痕 | ✅ 存在 | 与 `audit_event.py` 联动 |
| 分享链路 | ✅ 通 | `share_report.py` / `share_public.py` |

**结论**：**这是全项目完成度最高、设计最正确的板块**。上轮已确认 region_guard 接线 16 处（diagnosis×4 / gdpr×5 / genome×3 / observations×4）。

---

## 三、是否符合人类使用习惯

| 维度 | 评价 | 说明 |
|---|---|---|
| 合规透明 | ⚠️ | 用户可能不理解"为什么我的报告少了几段"→ 应提示"根据您所在地区规范，部分内容未展示" |
| **合规与有用的平衡** | ❌ **最大风险** | 严格过滤（尤其 EU 策略"几乎仅保留 lifestyle"）后报告可能**读起来很空**，用户价值骤降 |
| 分享体验 | ✅ 好 | 分享是最强增长动作，已有独立页面 |
| 免责声明疲劳 | ⚠️ | 大量免责声明会让用户跳过所有提示 |

**最需要改的一条**：**"合规且有用"的文案策略**。合规过滤的默认值应该是"**改写为合规但仍有信息量的表述**"，而不是"删除"。字段级过滤应配置 fallback 文案——这是当前未见的能力，也是决定这个板块是"护城河"还是"价值杀手"的分水岭。

---

## 四、市场与竞品对标

### 🔴 重要修正：不能说"国际空白"

**多法域 claims 过滤分层看**：
- **闭源 SaaS 层有直接反例**：Veeva Vault PromoMats、Klick Guardrail、RegASK、Regasis / Food Compliance——全部面向**制药 MLR、食品/补充剂标签**；
- **"面向 wellness 报告生成、可编程、覆盖中/美/英/澳/欧五法域"这一层，检索未见任何开源或 API 化对标**。

→ **这是真实但很窄的空位。对外表述应精确**：不要说"国际空白"（会被 Veeva 打脸），应说"**面向 wellness 报告的可编程多法域 claims 过滤层，未见开源或 API 化对标**"。

| 对象 | 定位 | 说明 |
|---|---|---|
| Veeva Vault PromoMats | 制药 MLR 内容审批 | 成熟极高，制药营销向 |
| Klick Guardrail | 宣称库 + MLR 决策智能 | 仍是制药语境 |
| RegASK | Agentic AI 全球法规情报 | 偏食品、化妆品、补充剂 |
| Function Health / Superpower | 健康报告 | **完全不碰法域合规** |

### 监管时序（2026 最新）
| 事件 | 时间 | 影响 |
|---|---|---|
| **FDA《General Wellness: Policy for Low Risk Devices》终版** | **2026-01-06** | 低风险一般健康产品**不执行 510(k)/QSR/MDR** → 窗口变宽 |
| EU MDCG 2019-11（Rule 11） | 现行 | 软件定性与分类主依据 |
| Implementing Regulation (EU) 2026/977 | 2026-05-05 | — |
| **EU AI Act（Digital Omnibus 2026-05-07 临时协议）** | 多数高风险义务推迟至 **2027-12-02**；透明度义务 **2026-08-02** 仍生效 | 合规窗口延长（二手来源，待核） |
| 中国 NMPA"人工智能+药品监管"实施意见 | 2026-04-02 | 国内监管加码 |

---

## 五、可融合的开源技术

**检索结论：未检索到 claims 过滤引擎级开源项目。** 可拼装件：

| 项目 | 许可 | 活跃度 | 能解决什么 | 集成成本 | 建议 |
|---|---|---|---|---|---|
| **Microsoft Presidio** | MIT | 活跃 | PII 识别与脱敏 | 低 | 报告导出前脱敏 |
| **OpenMed** | Apache-2.0 | 近期活跃 | 本地临床 NER + HIPAA 去标识 | 中 | 医疗实体识别 |

**取舍**：
- 报告渲染：用现成模板引擎，**别自研**。
- **claims 规则库：必须自研**，它是资产。
- 实体识别层：直接用 Presidio / OpenMed，**别训模型**。

---

## 六、提升方案

### P0（1–2 周）

| 项 | 动作 | 验收标准 |
|---|---|---|
| P0-1 | **字段级 fallback 文案**：被过滤字段改为"合规但仍有信息量"的替代表述，而非删除 | 5 个法域各有 fallback 表；EU 策略下报告仍有实质内容 |
| P0-2 | 用户可见的合规提示："根据您所在地区规范，部分内容未展示" | 用户不困惑于内容缺失 |
| P0-3 | claims 策略变更的**回归测试集**（每法域 ≥ 20 条断言） | 策略改动触发测试 |

### P1（3–6 周）

| 项 | 动作 | 验收标准 |
|---|---|---|
| P1-1 | 引入 Presidio 做报告分享前的 PII 脱敏 | 分享链接不含可识别信息 |
| P1-2 | claims 规则**版本化**并与审计报告关联 | 能回答"某份报告当时用的是哪版策略" |
| P1-3 | 新增法域的扩展机制文档化 | 加第 6 个法域不需改引擎代码 |

### P2（2–4 月）

| 项 | 动作 | 验收标准 |
|---|---|---|
| P2-1 | 对外输出"合规解释层"能力（对齐 M14 MCP） | B 端客户可调用 claims 过滤 |
| P2-2 | 追踪 FDA GW 终版与 EU AI Act 时间表变化，策略同步 | 有监管变更的跟踪与更新流程 |

---

## 七、板块评分

| 维度 | 分 | 说明 |
|---|---|---|
| 流程走通性 | 9/10 | 5 法域 + fail-closed + 端点/字段双层 + 审计留痕 |
| 人类使用习惯 | 5/10 | **"合规但很空"是价值杀手**，需 fallback 文案 |
| 竞品对标 | 7/10 | 真实但窄的空位（不可宣称"国际空白"） |
| 技术深度 | 8/10 | 全项目最强壁垒层 |
| **综合** | **7.5/10** | **定位：唯一真正的护城河。下一步从"能过滤"升级到"过滤后仍有用"** |
