# HealthLens Powered-by B2B 解释层规范（S3-2）

> 目标：把八轴解释能力 + 合规输出层封装为可对外嵌入的 B2B API，
> 复刻 Tiny Health 的 "Powered by" 商业路径。
>
> **状态**：API 契约就绪；商务谈判、SLA 签署、试点合同需外部执行。

## 1. 商业模型

**参考范本**：Tiny Health（B2B 解释层，20 万纵向样本 + 1 篇 RCT，
拿下 Mayo / Superpower / ZOE）。

**HealthLens 差异化**：
- 中医知识 + 中医国标术语映射（西方竞品缺）
- 五法域合规输出层（8/10 分，国际空白）
- 药食同源 + 处方安全性（十八反/十九畏/妊娠/中西药禁忌）
- 号脉硬件（ESP32 固件 + 舌象分析）

**目标客户**：L2 层（临床/整合医学平台），非 L1 消费者会员制。

## 2. API 契约（v1.0）

### 2.1 端点

```
POST https://healthlens.cc/powered/v1/score
  → 输入 raw health signals，输出八轴分 + 通路归因 + 干预建议

POST https://healthlens.cc/powered/v1/explain
  → 输入八轴分（外部已算好），输出解释文案 + 免责声明 + 法域过滤

POST https://healthlens.cc/powered/v1/simulate
  → 输入 baseline + 干预杠杆，输出反事实轨迹 + 校准 + 敏感性

POST https://healthlens.cc/powered/v1/validate
  → 输入药物 + 基因组，输出相互作用/禁忌/表达表型

GET  https://healthlens.cc/powered/v1/axes/schema
  → 返回八轴定义 + 阈值参数 + 术语映射（元数据）

GET  https://healthlens.cc/powered/v1/jurisdictions
  → 返回支持的合规法域列表 + 每法域的字段策略
```

### 2.2 请求/响应格式

所有端点使用 JSON，UTF-8 编码。请求头：

```
Authorization: Bearer <api_key>
Content-Type: application/json
X-Client-Id: <partner_id>
X-Request-Id: <trace_id>         # 客户方生成，便于双向追踪
```

响应头：

```
X-HealthLens-Version: <version>   # 服务版本
X-HealthLens-Processed-At: <iso8601>
X-HealthLens-Disclaimer-Attached: true/false
```

### 2.3 核心端点示例

#### POST /powered/v1/score

请求：
```json
{
  "biomarkers": {
    "glucose": 6.4, "hba1c": 6.1, "crp": 0.8, "tg": 1.6, "hdl": 1.2,
    "bmi": 26.5, "waist": 92
  },
  "wearable": {
    "hrv_rmssd": 45, "resting_hr": 68, "steps_avg": 6500
  },
  "symptoms": ["fatigue", "insomnia"],
  "jurisdiction": "cn"
}
```

响应：
```json
{
  "success": true,
  "not_clinical": true,
  "axes": {
    "A": {"score": 62, "measured": true, "penalty_ratio": 0.38},
    "F": {"score": 55, "measured": true, "penalty_ratio": 0.45},
    "G": {"score": 88, "measured": true, "penalty_ratio": 0.12}
  },
  "weak_axes": ["A", "F"],
  "overall_score": 68.33,
  "pathways": [
    {"name": "AMPK-mTOR", "axis": "A", "score": 62, "signal": "impaired"}
  ],
  "interventions": [
    {"type": "food_medicine", "target": "A", "ingredients": ["山药", "白术"]}
  ],
  "disclaimer": "本结果为 wellness 参考，不构成诊断或治疗建议...",
  "version": "0.26.2"
}
```

#### POST /powered/v1/explain

请求：
```json
{
  "axes": {"A": 62, "F": 55, "G": 88},
  "jurisdiction": "us",
  "context": "report_intro"
}
```

响应：
```json
{
  "success": true,
  "explanations": {
    "A": {"label": "气化-自噬稳态", "narrative": "..."},
    "F": {"label": "炎症负荷", "narrative": "..."}
  },
  "filtered_fields": ["severity", "risk_probability"],
  "fallback_fields": {
    "severity": {"label": "关注程度", "value": "需关注"},
    "risk_probability": {"label": "健康关注指数", "value": "中等关注"}
  },
  "disclaimer": "This wellness assessment is for informational purposes..."
}
```

## 3. API Key 分级

| 层级         | 用途               | 额度          | 价格    | 支持法域    |
| ------------ | ------------------ | ------------- | ------- | ----------- |
| `sandbox`    | 开发测试           | 100 req/day   | 免费    | 仅 CN        |
| `starter`    | 单机构小规模       | 10K req/day   | 月付    | CN + EU     |
| `partner`    | 中型平台           | 100K req/day  | 季度    | CN + US + EU |
| `enterprise` | 大型连锁/多法域    | 1M req/day+   | 年度    | 全法域       |

## 4. 鉴权与安全

- **API Key 格式**：`hl_b2b_<env>_<tier>_<random_32>`（env = prod/staging）
- **权限模型**：Key 绑定 tier、法域白名单、QPS 上限、endpoint 白名单
- **签名验证**（可选）：企业级 key 可启用 HMAC-SHA256 请求签名
- **审计**：每次调用写入 `AuditEvent`（who/when/what/region/outcome）
- **限流**：Redis + 令牌桶（每 key 独立桶，防止跨客户挤压）

## 5. 认证接口骨架（可落地实现）

新增文件（S3-2 阶段 3-4 周完成）：

```
app/api/powered/
├── __init__.py
├── keys.py              # API key CRUD + tier 管理
├── scoring.py           # /powered/v1/score
├── explain.py           # /powered/v1/explain
├── simulate.py          # /powered/v1/simulate
├── validate.py          # /powered/v1/validate
├── metadata.py          # /powered/v1/axes/schema, /jurisdictions
└── middleware/
    ├── api_key_auth.py  # API key 验证中间件
    ├── rate_limiter.py  # 令牌桶限流
    └── audit.py         # 审计写入
```

数据模型（新增）：

```python
class ApiKey(Base):
    id: str
    partner_id: str            # B2B 客户 ID
    key_hash: str              # SHA256(api_key)
    tier: str                  # sandbox/starter/partner/enterprise
    jurisdictions: list[str]   # 允许法域
    rate_limit_rpm: int
    rate_limit_daily: int
    endpoints: list[str]       # 允许的端点
    expires_at: datetime | None
    is_active: bool
    last_used_at: datetime | None

class Partner(Base):
    id: str
    name: str
    contact_email: str
    tier: str
    onboarding_status: str     # pending/active/suspended
    jurisdiction_whitelist: list[str]
    sl_sla_level: str          # bronze/silver/gold
```

## 6. SLA 与商用条款（骨架）

| 级别   | 可用性    | 响应时间     | 支持      | 数据保留    |
| ------ | --------- | ------------ | --------- | ----------- |
| Bronze | 99.0%     | 2 分钟内 5xx | 工单      | 30 天       |
| Silver | 99.5%     | 5 分钟       | 邮件      | 90 天       |
| Gold   | 99.9%     | 5 分钟 P1    | 专属技术对接 | 1 年      |

## 7. 试点启动方案

**目标**：3 家试点，验证市场与技术。

| 目标客户类型       | 候选               | 试点重点              | 优先级 |
| ------------------ | ------------------ | --------------------- | ------ |
| 整合医学诊所       | L2 层诊所联盟      | 中医合规解释          | 高     |
| 长寿诊所           | 类 Fountain Life   | 生物年龄 + 干预       | 中     |
| 传统医学平台       | WHO TCIM 生态内    | 术语国标映射          | 高     |

**试点合同**（3 个月免费）：
- 免费 tier + 24 小时工单
- 联合署名发表机会（若产生数据成果）
- 反馈换取商业折扣

## 8. 与 Tiny Health 差异

| 维度           | Tiny Health         | HealthLens                     |
| -------------- | ------------------- | ------------------------------ |
| 核心资产       | 微生物组测序        | 八轴 + 中医国标映射 + 合规     |
| 数据量         | 20 万纵向样本       | 0 纵向（S2-2 待启动）          |
| RCT            | 1 篇（Nature 2024） | 无                             |
| 解释层卖点     | Shotgun 宏基因组    | 五法域合规 + 药食同源 + 号脉   |
| 目标客户       | Mayo / ZOE          | L2 整合医学平台                |
| 融资           | $33M B              | 独立开源                       |

## 9. 未闭合（诚实）

- **需要真实商务谈判**：AI 无法发起合同签署
- **需要试点客户**：3 家试点是市场验证的必要条件
- **需要 SLA 法务审核**：本 SLA 骨架需专业法务审核
- **需要定价数据**：无真实付费数据前，定价仅为示意
- **需要 3-4 周工程投入**：认证接口骨架已设计，需工程落地
