# Open Wearables × HealthLens 集成方案

> 研究日期：2026-09-22 | 版本：v1.0

---

## 一、现状诊断

### 1.1 现有连接器状态

| 连接器 | 状态 | 真实 API 调用 | 数据来源 |
|--------|------|--------------|---------|
| `apple_health.py` | XML 导入骨架 | ❌ 需 iOS App 导出 XML | HealthKit |
| `huawei_health.py` | Phase 1 mock | ❌ 返回模拟数据 | 华为健康 |
| `withings.py` | Phase 1 mock | ❌ 返回模拟数据 | Withings |
| `xiaomi_health.py` | Phase 1 mock | ❌ 返回模拟数据 | 小米运动 |
| `hospital_lis.py` | 占位 | ❌ | 医院 LIS |

**核心问题**：5 个连接器全部是 mock/stub，没有一个真正调用 provider API。每个连接器都要各自实现 OAuth 流程 + token 刷新 + 数据格式转换 + webhook 处理，工作量极大且脆弱。

### 1.2 HealthLens 数据模型

- **HealthObservation**：LOINC 编码 + 数值/字符串 + 来源 + 时间戳
- **SleepRecord**：睡眠阶段（深睡/浅睡/REM/觉醒）、HRV、效率、环境参数
- **RepairScore**：7 维度评分（深睡 25% / HRV 20% / 炎症 15% / 运动 15% / 营养 10% / 节律 10% / 精力 5%）

### 1.3 部署架构

```
ECS 150.158.119.19
├── healthlens-net (bridge)
│   ├── healthlens-web      (FastAPI :8000)
│   ├── healthlens-worker   (Celery worker)
│   ├── healthlens-db       (TimescaleDB :5432)
│   ├── healthlens-redis    (Redis :6379)
│   └── healthlens-minio    (MinIO :9000)
```

---

## 二、Open Wearables 能力评估

### 2.1 项目状态（2026-09-22 实测）

| 指标 | 值 |
|------|-----|
| 版本 | 0.9（Sep 17, 2026） |
| 许可 | MIT |
| 最新 commit | Sep 21, 2026 |
| 技术栈 | FastAPI + PostgreSQL + Redis + Celery |
| Python | 3.14 |
| 前端 | React + TanStack Start + TypeScript |

### 2.2 支持的 Provider（14 个）

**Cloud-based（OAuth 云同步）**：
| Provider | 支持状态 | 特点 |
|----------|---------|------|
| Garmin | ✅ | webhook-only delivery |
| Oura | ✅ | 戒指，睡眠/HRV 最强 |
| WHOOP | ✅ | 带（band），恢复/压力 |
| Polar | ✅ | 运动手表 |
| Suunto | ✅ | 运动手表 |
| Ultrahuman | ✅ | 智能戒指 |
| Strava | ✅ | 运动记录 |
| Fitbit | ✅ | 运动手表 |
| Withings | ✅ | 体脂秤/血压计 |
| Google Health | ✅ | Fit API 替代 |

**SDK-based（需移动端）**：
| Provider | SDK | 备注 |
|----------|-----|------|
| Apple Health | iOS/Flutter/RN/Android | HealthKit，无云端 API |
| Samsung Health | Android/Flutter/RN | 韩国主流 |
| Google Health Connect | Android | Google Fit 替代 |

**额外**：Apple Health XML Import（支持 S3 分块上传大文件）

### 2.3 API 端点

```
# 用户管理
GET  /api/v1/users
GET  /api/v1/users/{user_id}

# 摘要数据
GET  /api/v1/users/{id}/summaries/daily
GET  /api/v1/users/{id}/summaries/sleep
GET  /api/v1/users/{id}/summaries/activity
GET  /api/v1/users/{id}/summaries/recovery
GET  /api/v1/users/{id}/summaries/body

# 事件数据
GET  /api/v1/users/{id}/events/workouts
GET  /api/v1/users/{id}/events/sleep

# 时序数据
GET  /api/v1/users/{id}/timeseries

# OAuth 连接
GET  /api/v1/oauth/{provider}/authorize

# Webhook 注册
POST /api/v1/webhooks/endpoints
```

### 2.4 健康评分算法（0.4.3+，beta）

| 评分 | 算法 | 输入 |
|------|------|------|
| Sleep Score | 时长 40% + 睡眠阶段 20% + 一致性 20% + 中断 20% | 睡眠摘要 |
| Resilience Score | HRV-CV（心率变异系数变异） | 7 晚窗口 |
| Recovery Score | 多因素恢复 | 睡眠 + HRV + 压力 |
| Strain Score | 运动负荷 | 活动摘要 |
| VO2 Max | 估算 | 活动 + 心率 |

> ⚠️ 评分算法在 beta 阶段，适合内部原型，不直接面向用户展示。

### 2.5 MCP Server（5 个工具）

| 工具 | 功能 |
|------|------|
| `get_users` | 查询用户列表 |
| `get_workout_events` | 获取运动事件 |
| `get_sleep_summary` | 获取睡眠摘要 |
| `get_activity_summary` | 获取活动摘要 |
| `get_timeseries` | 获取时序数据（HRV/SpO2/体重等） |

---

## 三、集成架构设计

### 3.1 方案：Open Wearables 作为统一中间层

```
┌─────────────────────────────────────────────────────────┐
│  HealthLens Frontend (React SPA)                        │
│  healthlens-a3w.pages.dev                               │
└─────────────┬───────────────────────────────────────────┘
              │ REST API
              ▼
┌─────────────────────────────────────────────────────────┐
│  HealthLens Backend (FastAPI)                            │
│  /opt/healthlens/  docker-compose                         │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  /api/v1/connections/*                          │    │
│  │  /api/v1/observations/*                         │    │
│  │  /api/v1/axes/*                                 │    │
│  │  /api/v1/agent/*                                │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  app/connectors/open_wearables.py               │    │
│  │  ──── HTTP client to Open Wearables ────        │    │
│  │  ├─ fetch_sleep_summaries()                     │    │
│  │  ├─ fetch_activity_summaries()                  │    │
│  │  ├─ fetch_workout_events()                      │    │
│  │  └─ fetch_timeseries()                          │    │
│  └────────────────────┬────────────────────────────┘    │
└───────────────────────┼─────────────────────────────────┘
                        │ REST API (X-Open-Wearables-API-Key)
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Open Wearables (FastAPI)                               │
│  /opt/open-wearables/  docker-compose                     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  :8001 API (port shift to avoid clash)          │    │
│  │  ──── Normalization Layer ────                   │    │
│  │  ├─ Garmin ───┐                                 │    │
│  │  ├─ Oura ────┐│                                  │    │
│  │  ├─ WHOOP ──┐││                                 │    │
│  │  ├─ Polar ──┐│││                                 │    │
│  │  ├─ ...     ┐││││                                 │    │
│  │  └──────────┘││││                                  │    │
│  │              ▼▼▼▼                                   │    │
│  │  Unified Schema (sleep/workout/activity/body)      │    │
│  │  + Health Scores (sleep/recovery/strain)          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  PostgreSQL + Redis + Celery (自有实例)                   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 为什么不需要自建 OAuth

| 自建 OAuth（现状） | Open Wearables 中间层（提案） |
|-------------------|-----------------------------|
| 每个 provider 写一套 OAuth | 一套统一 API |
| token 刷新各自处理 | OW 内部自动刷新 |
| 数据格式各异，各写转换器 | OW 统一 schema |
| webhook 各自接 | OW 统一 webhook |
| Garmin 6h token 过期 | OW 内部处理 |
| Apple Health 需 SDK | OW 提供 SDK |
| 5 个 mock，0 个可用 | 14 个 provider 真实可用 |

---

## 四、部署方案

### 4.1 ECS 资源评估

当前 ECS 150.158.119.19（Ubuntu 22.04 + Docker）：
- 已运行：HealthLens（web + worker + db + redis + minio）= 5 容器
- Open Wearables 新增：backend + frontend + db + redis + celery = 5 容器
- 总计 10 容器，需评估内存/磁盘

### 4.2 Docker Compose 共存方案

```yaml
# /opt/open-wearables/docker-compose.yml
# 关键配置：
# - 端口 :8001（避免与 HealthLens :8000 冲突）
# - 独立 PostgreSQL 实例
# - 独立 Redis 实例

services:
  backend:
    ports:
      - "8001:8000"   # OW API → :8001
    environment:
      - OPEN_WEARABLES_PORT=8001
  # ... 其余标准 OW 配置
```

### 4.3 网络方案

**方案 A：独立 bridge 网络**
```
healthlens-net  ── healthlens-web:8000
ow-net          ── ow-backend:8001

ow-backend → healthlens-web: 通过宿主机 IP 访问
```

**方案 B：共用 bridge 网络（推荐）**
```
healthlens-net ── healthlens-web:8000  ── ow-backend:8001
                   healthlens-db:5432   ow-db:5433
                   healthlens-redis:6379 ow-redis:6380
```

### 4.4 资源需求

| 组件 | 内存 | 磁盘 |
|------|------|------|
| OW Backend (FastAPI) | ~200MB | ~50MB |
| OW Frontend (React) | ~100MB | ~30MB |
| OW PostgreSQL | ~200MB + 数据 | ~100MB |
| OW Redis | ~50MB | ~20MB |
| OW Celery Worker | ~200MB | ~50MB |
| **合计** | **~750MB** | **~250MB** |

> 如果 ECS 内存 < 4GB，建议方案 B 共用网络但 OW 用较旧/较小的 PG/Redis 配置。

---

## 五、集成代码设计

### 5.1 OpenWearablesConnector

```python
# app/connectors/open_wearables.py

class OpenWearablesConnector(BaseConnector):
    SOURCE_TYPE = "open_wearables"
    DISPLAY_NAME = "Open Wearables (14 devices)"

    def __init__(self):
        self.api_url = settings.OPEN_WEARABLES_API_URL  # http://localhost:8001
        self.api_key = settings.OPEN_WEARABLES_API_KEY

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """从 OW 拉取归一化数据"""
        # 1. GET /api/v1/users/{id}/summaries/sleep → SleepRecord
        # 2. GET /api/v1/users/{id}/summaries/activity → HealthObservation
        # 3. GET /api/v1/users/{id}/events/workouts → HealthObservation
        # 4. GET /api/v1/users/{id}/timeseries → HealthObservation (HRV, SpO2, weight)

    async def sync_data(self, access_token: str, user_id: str, since: datetime) -> dict:
        """同步数据到 HealthLens HealthObservation 格式"""
        # 将 OW 的归一化数据映射到 HealthLens 的 LOINC 编码体系
```

### 5.2 数据映射表（OW → HealthLens）

| Open Wearables 字段 | HealthLens LOINC | 目标模型 |
|---------------------|------------------|---------|
| `sleep.total_duration_min` | 93832-4 (Sleep) | SleepRecord.total_duration_min |
| `sleep.deep_sleep_min` | — | SleepRecord.deep_sleep_min |
| `sleep.rem_sleep_min` | — | SleepRecord.rem_sleep_min |
| `sleep.sleep_efficiency` | — | SleepRecord.sleep_efficiency |
| `sleep.hrv_avg` | 8867-4 (HR) | SleepRecord.hrv_avg |
| `activity.steps` | 90536-5 (Steps) | HealthObservation |
| `activity.calories` | 41981-2 (Active Energy) | HealthObservation |
| `activity.heart_rate_avg` | 8867-4 (HR) | HealthObservation |
| `body.weight_kg` | 29463-7 (Body Mass) | HealthObservation |
| `body.body_fat_pct` | 8867-4 (HR→Fat) | HealthObservation |
| `timeseries.spo2` | 59408-5 (SpO2) | HealthObservation |
| `timeseries.hrv` | 8867-4 (HR→HRV) | HealthObservation |
| `timeseries.respiratory_rate` | 9279-3 (Resp Rate) | HealthObservation |

### 5.3 与八轴引擎的联动

| 八轴 | OW 数据来源 | 映射逻辑 |
|------|-------------|---------|
| A 气化/自噬 | `activity.calories`, `activity.intensity_minutes` | 能量代谢活跃 → 气化能力 |
| B 气血/线粒体 | `timeseries.hrv`, `sleep.hrv_avg` | HRV 高低 → 线粒体功能 |
| C 络脉/清瘀 | `body.weight`, `body.body_fat_pct` | 体脂趋势 → 清瘀能力 |
| D 阴阳/昼夜 | `sleep.bedtime`, `sleep.wake_time`, `sleep.consistency` | 睡眠规律 → 昼夜节律 |
| E 脏腑/神经内分泌 | `sleep.stress_score`, `timeseries.respiratory_rate` | 压力/呼吸 → 神经内分泌 |
| F 正邪/炎症 | `sleep.recovery_score`, `sleep.awakenings_count` | 恢复/中断 → 炎症水平 |
| G 神/情志 | `sleep.sleep_score`, `sleep.subjective_score` | 睡眠评分 → 神志状态 |
| H 先天/肾精 | `sleep.total_duration`, `sleep.deep_sleep_min` | 深睡时长 → 肾精储备 |

---

## 六、实施路线图

### Phase 0：部署 Open Wearables（~2 小时）
1. `git clone https://github.com/the-momentum/open-wearables.git`
2. 配置 `.env`，端口改为 8001
3. `docker compose up -d`
4. 验证 `curl http://localhost:8001/api/v1/health`
5. 创建 API key（管理面板 :3001）

### Phase 1：连接器代码（~1 天）
1. 新增 `app/connectors/open_wearables.py`
2. 配置项：`OPEN_WEARABLES_API_URL` + `OPEN_WEARABLES_API_KEY`
3. 数据映射：OW schema → HealthObservation / SleepRecord
4. 注册到 `ALLOWED_SOURCE_TYPES`

### Phase 2：前端接入（~1 天）
1. Profile 页新增「连接可穿戴设备」区块
2. 选择 provider → OAuth 跳转 → 回调 → 存储连接
3. 手动同步按钮 + 同步状态展示

### Phase 3：八轴联动（~0.5 天）
1. 将 OW 数据映射到 8 轴输入
2. 验证融合引擎消费路径

### Phase 4：验证 + 部署（~0.5 天）
1. 本地端到端测试
2. ECS 部署
3. 生产验证

---

## 七、成本分析

| 项目 | 自建 OAuth × 14 providers | Open Wearables 中间层 |
|------|--------------------------|----------------------|
| 开发工时 | 6-8 人周 | 2-3 人天 |
| 维护成本 | 每个 provider API 变更都要跟 | OW 统一处理 |
| 基础设施 | 同 ECS 成本 | 同 ECS + ~750MB RAM |
| 许可费 | 0 | 0（MIT） |
| 用户费 | $0.5-2/用户/月（如果用 SaaS） | $0（自托管） |
| 数据主权 | 自有 | 自有 |

---

## 八、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| OW 版本 < 1.0，API 可能变 | 中 | pin 到 git tag，监控 changelog |
| ECS 内存不足 | 中 | 先本地测，ECS 用最小配置 |
| 评分算法 beta 不稳定 | 低 | 不用 OW 评分，用原始数据 |
| Garmin/WHOOP OAuth 凭据需申请 | 低 | 先用 mock seed 数据开发 |
| HealthLens OW 端口冲突 | 低 | OW 改 :8001，隔离清晰 |

---

## 九、结论

**推荐方案**：部署 Open Wearables 作为统一中间层，通过单一 `OpenWearablesConnector` 接入 HealthLens。

**核心理由**：
1. 技术栈完全匹配（FastAPI + PG + Redis + Celery + Docker）
2. 现有 5 个 mock 连接器全部可替代
3. 14 个 provider 一次覆盖（Garmin/Oura/WHOOP/Polar/Suunto/...）
4. MIT 许可，零许可费，零用户费
5. 自带 MCP server，可与 AI Agent 直接交互
6. 部署在 ECS 上，数据不出自己的服务器

**下一步**：等你确认方向后，我开始 Phase 0（部署 OW）+ Phase 1（连接器代码）。
