# HealthLens 打地基·啃硬骨头专项评估报告

> 基线：v0.30.0（2026-10-16）｜评估方式：**全部实证，零猜测试**
> 语气说明：本报告刻意不写成绩。楼已经够高，问题在承重墙。

---

## 0. 先说结论

> **测试 1669 全绿。但这 1669 个测试保护的 schema，和生产实际用的 schema，已经分叉了 36 张表。**

这不是"还有优化空间"。这是**结构性的假绿**：CI 每次都说通过，而一次全新的 `docker-compose` 部署，**连用户注册都跑不通**。

我在空库上跑了一遍 `alembic upgrade head`（也就是 `docker-compose.yml:149` 生产初始化的第一条命令），然后启动应用注册用户：

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: users.is_active
[SQL: SELECT users.email, ..., users.is_active, users.nickname, users.utm_source, ...
       FROM users WHERE users.email = ?]
[parameters: ('probe_x@healthlens.com',)]
```

**一个新环境部署完，第一个用户注册失败。**

而同一时刻，`pytest tests/` → `1669 passed, 2 skipped, 0 failed`。

---

## 1. F1｜数据库迁移与 ORM 全面漂移（最致命的承重墙裂缝）

### 1.1 事实（实测）

| 指标 | 数值 |
|---|---|
| ORM 声明表数（`app/models/*.py` 的 `__tablename__`） | **61** |
| `alembic/versions/` 实际建表数 | **24**（+`alembic_version` = 25） |
| **无迁移的表** | **37 张（61%）** |
| 迁移文件数 | 6（最后一份 `006_add_region_jurisdiction`） |
| `tests/` 下提及 alembic 的测试文件 | **0** |
| CI（11 个工作流）里跑 alembic 的步骤 | **0** |
| `.pre-commit-config.yaml` | **不存在** |

### 1.2 缺迁移的表——恰好是整个新战略的核心

```
SVIEE 证据核心（L1/L2/L3 全灭）：
  longitudinal_studies, axis_snapshots, intervention_events, biomarker_readings
合作方生态（"Powered by HealthLens"）：
  partners, partner_api_keys
隐私同意（GDPR/PIPL 叙事的底座）：
  field_consents
积分与裂变：
  user_points, point_orders, point_packages, point_rules, point_transactions,
  referral_tiers, referral_relationships, referral_rebates
内容与转化：
  seo_pages, seo_page_templates, keyword_clusters, conversion_records,
  analytics_events, analytics_sessions
中医知识资产：
  tcm_classical_books, classical_formulas, tcm_syndrome_mappings,
  cellular_pathways, gene_variants, protein_annotations, repair_scores,
  food_therapy_recipes, therapeutic_interventions, non_pharma_treatments
其他：
  invite_codes, verification_codes, sleep_records, sleep_checklists,
  share_records, shared_reports
```

**这不是"忘了补几张表"。这是把过去两个月的全部战略增量，建在了一条从没被执行过的部署路径上。**

### 1.3 列级也漂了

`users` 表 alembic 只建 12 列：`id, email, phone, password_hash, role, created_at, updated_at, totp_secret, totp_enabled, otp_method, region, jurisdiction`

ORM 需要 18 列。缺：**`is_active, nickname, utm_source, utm_medium, utm_campaign, referral_code`**。

### 1.4 为什么它能一直绿着（这是最该记住的一条）

```
tests/conftest.py:32     await conn.run_sync(Base.metadata.create_all)   ← 测试：永远 61 张表
docker-compose.yml:149   sh -c "alembic upgrade head && ..."             ← 生产：只有 24 张表
app/main.py              （无 create_all，无启动建表兜底）                  ← 应用：谁都不建
```

**两条 schema 来源，分叉 36 张表，零测试覆盖分叉本身。**

### 1.5 附带发现：真实生产库本身也是孤儿

`data/healthlens.db` 有 25 张表、**没有 `alembic_version` 表**。这意味着这个库从来不是 alembic 建的，是更老版本的 `create_all` 产物——它连 24 张都对不上（含 `tongue_images`、`tcm_delivery_orders` 等当前 ORM 已不存在的表名）。**生产库、迁移、ORM 三方互不匹配。**

---

## 2. F2｜"装了重型库的世界"从未被执行（dowhy bug 的家族病）

昨天我修了 `dowhy_adapter.py:399`：`dowhy_mode="dowhy"` 时 `dowhy_pkg` 恒为 None → 严格 DoWhy 模式是死代码。

今天挖出根因，它不是孤例：

```python
app/lib/federated/flower_adapter.py:53
try:  # pragma: no cover - 依赖存在性由 monkeypatch 测试覆盖
    import flwr
    FLWR_AVAILABLE = True
except ImportError:
    FLWR_AVAILABLE = False
```

- `# pragma: no cover` —— **"装上了 flwr"这条分支，覆盖率工具被明确告知不要看**
- FLWR_AVAILABLE 是模块级布尔，读在调用期（这点比 dowhy 幸运，可 monkeypatch）
- 但其上游逻辑与 dowhy 同一个模式：**在 CI 环境里重型库永远不存在 → 重型分支永远不执行 → 该分支里的 bug 永远不会被发现**

昨天 dowhy 那个 bug，正是在"装了 dowhy"的分支里，静默地把 `reuthers` 全部标成 `pure_python`。

**这不是巧合，是系统性盲区：CI 装不上重型库 → 该分支代码是死代码 → 死代码里的逻辑错误无法被发现 → 而报告会照样写"用 DoWhy 做的证伪"。**

对一个要把 `refutation 三项全部通过` 写进用户可见输出的系统，这是**学术诚信级别的风险**。

---

## 3. F3｜无 lock 文件 + 无上界依赖（可复现性为零）

### 3.1 事实

`requirements.txt` 全部 `>=`，且核心库**连下界都没有**：

```diff
  fastapi          ← 无任何约束
  uvicorn          ← 无任何约束
  sqlalchemy[asyncio]>=2.0    ← 无上界
  python-jose[cryptography]   ← 无任何约束
  pydantic>=2.0              ← 无上界
  ...（22 项，无一项有上界）
```

仓库内**无 lock 文件、无 constraints 文件**。

`requirements.txt` 头部注释自称 "Synced with pyproject.toml — update both files together"——但 `pyproject` 里有 `pyyaml>=6.0`，`requirements.txt` 里没有；反过来 `requirements.txt` 的 22 项与 pyproject 的 26 项也不一致。**两个清单本身就是漂移的。**

### 3.2 为什么这对本项目尤其致命

本项目的核心科学主张是**"可计算 + 可复现"**：`engine_validation_metrics`、`validation_snapshots/`（快照带 git_sha）、Zenodo DOI、medRxiv 投稿包。整套叙事建立在"别人能复现我的数字"上。

**但今晚和三个月后执行 `pip install -r requirements.txt`，装出来的不是同一个系统。** 一个 `fastapi` minor 或 `pydantic` patch 就能让八轴分数或 FHIR 序列化静默变化——而你的指标文件不会变，看的是代码里同样静默的变化。

对外发表"可复现计算"，手里没有 lock 文件，审稿人一问就穿。

---

## 4. F4｜安全与稳定性的硬结构缺口

| # | 发现 | 位置 | 等级 |
|---|---|---|---|
| S1 | CORS 默认 `["*"]`，仅 `warnings.append()` 不阻断 | `app/config.py:15, 276` | 高 |
| S2 | **生产代码**里 mock 服务 CORS 全开 `allow_origins/methods/headers=["*"]` | `app/mock/mock_open_wearables.py:17` | 高 |
| S3 | `app/api/edge_ticket.py` 9 处 `except Exception`（票据/边缘设备链路） | 全仓 218 处 | 中 |
| S4 | `app/tasks/acquisition_tasks.py` 13 处 `except Exception`（数据采集任务） | 同上 | 中 |
| S5 | pydantic 字段名 `schema` 遮蔽父类 `BaseModel` 属性 | `app/api/timeseries.py:76` | 低 |
| S6 | 三道闸门全缺：无 pre-commit、无 lock、CI 不跑迁移 | — | 高 |

S3/S4 值得单独说：**采集链路吞异常 = 静默丢数据**。对一个要把"数据不出域"当卖点的系统，数据在自己这边被悄悄丢掉，比被偷更难发现。

---

## 5. 为更高的楼层预埋的结构（你现在就要加，否则 Federated 一上来就返工）

这一节直接回答你的问题：楼还要往上盖，哪些承重结构必须在现在就加。

### 5.1 乐观并发控制（联邦模式一上来立刻需要）

`longitudinal_studies` / `axis_snapshots` 现在是裸表。联邦多租户同时写同一个 study 的快照时：

- 无 `version_id` → last-write-wins，**后到的数据静默覆盖先到的**
- 多机构并发 → 竞态，且 SQLite 下写锁会让整个 API 阻塞

**预埋**：`axis_snapshots` 加 `version_id: int`，更新用 `UPDATE ... WHERE id=? AND version_id=?`，影响行数 0 即返 409。**现在加是 1 个字段，联邦上线后加是数据迁移。**

### 5.2 幂等键（联邦重复提交的防波堤）

`biomarker_readings` 需要唯一索引 `(study_id, ts_utc, channel_name)`。联邦场景下同一份数据可能被重传（重试、网络抖动、租户重复注册）。**没有幂等键，"联邦聚合"会把同一个个体的同一时刻算三遍**——而这会直接污染你要发表的效应估计。

### 5.3 迁移可回滚（现在 6 个迁移全是单向）

生产环境没有 `downgrade` 路径 = 出问题只能手工修库。至少从新迁移开始写 `downgrade()`，并在 CI 里测 `alembic downgrade -1` → `upgrade head` 往返。

### 5.4 Schema 契约测试（一条测试锁死未来所有漂移）

```python
# tests/test_schema_parity.py
def test_alembic_schema_matches_orm():
    # 1. 空内存库跑 alembic upgrade head
    # 2. 对比 Base.metadata.tables 与 PRAGMA table_info
    # 3. 缺任何表/列 → FAIL
```

**这一条测试，是本次报告里投入产出比最高的一件事。** 它把 F1 从"人工记得补迁移"变成"忘了就红"。

### 5.5 采集链路的 fail-loud

`except Exception` 在采集链路应改为：记录 + 计数 + 上报（已有 prometheus-client），**至少要让"丢了请求数据"这件事可见**，而不是静默返回空。

---

## 6. 打地基执行清单（按啃的顺序）

### 第一批：D0 迁移真源化（3–5 天，最高优先级）

| # | 动作 | 验收标准 |
|---|---|---|
| D0-1 | 对现有 6 个迁移与 `Base.metadata` 做差异合并，生成 `007_align_orm_schema.py` | 空库 `alembic upgrade head` → **61 张表、`users` 18 列全在** |
| D0-2 | 新增 `tests/test_schema_parity.py` | 缺任一表/列 → 测试 FAIL |
| D0-3 | CI 加一步 `alembic upgrade head` + 跑 D0-2 | PR 里能看见迁移覆盖 |
| D0-4 | `axis_snapshots` 加 `version_id`；`biomarker_readings` 加唯一索引 `(study_id, ts, channel)` | D0-2 同时断言这两项存在 |
| D0-5 | 从 007 起所有迁移必须写 `downgrade()` | CI 跑 `upgrade → downgrade -1 → upgrade` 往返 |

> **D0-1 的做法建议**：用 `alembic revision --autogenerate` 对空库生成，**人工逐条 review**（autogenerate 在 SQLite 上对 rename/constraint 不可靠，会误报 drop）。不要无脑接受。

### 第二批：D1 消灭系统性假绿（2–3 天）

| # | 动作 | 验收标准 |
|---|---|---|
| D1-1 | conftest 改为双模式：默认 `create_all`（快）+ CI job 跑 `--schema-source=alembic` 全量 | 两条路径 schema 集合相等，由 D0-2 断言 |
| D1-2 | 为 dowhy/pymc/flwr/xgrammar/langfuse/ragas/biomni 建**真实接口 stub**（不是空 `ModuleType`） | 每个重型库的 `_AVAILABLE=True` 分支至少被执行一次 |
| D1-3 | 去掉所有 `# pragma: no cover` 于重型分支 | 覆盖率报告里重型分支可见 |
| D1-4 | 用 D1-2 的 stub 重跑 dowhy 严格模式 | `report.method == "dowhy"` **真的成立** |

> D1-2 是本次的第二颗种子。stub 必须实现**被真实调用的接口**（如 dowhy 的 `CausalModel.refute_estimate`），否则等于没测——dowhy 那个 bug 之所以溜过去，正是因为测试用空 `ModuleType` 只验证"import 成功"。

### 第三批：D2 依赖可复现（1 天）

| # | 动作 | 验收标准 |
|---|---|---|
| D2-1 | `pip-compile` 生成 `constraints.txt`；给 fastapi/pydantic/sqlalchemy/cryptography/python-jose 五项加上界 | Dockerfile 装时带 `-c constraints.txt` |
| D2-2 | `requirements.txt` 改由 pyproject 单一真源生成，删掉手写同步注释 | 两清单 diff 为空 |
| D2-3 | CI 加 job：`pip install -c constraints.txt && pytest` 通过 | — |

### 第四批：D3 安全硬结构（3–5 天）

| # | 动作 | 验收标准 |
|---|---|---|
| D3-1 | CORS 非 DEBUG 下默认改为空列表，启动时直接 fail（不再是 warning） | 用 `CORS_ORIGINS=["*"]` + `DEBUG=false` 启动 → 进程退出 |
| D3-2 | `mock_open_wearables.py` 收紧 CORS，仅允许本机/测试来源 | — |
| D3-3 | 218 处 `except Exception` 分三类审计，采集链路（S3/S4）改为"计数 + 指标 + 告警" | 丢数据变成可见指标 |
| D3-4 | 修 `timeseries.py:76` 字段名 `schema` 遮蔽 | 无 pydantic warning |

### 第五批：D4 为联邦预埋（与 D0 并行，各 1–2 天）

| # | 动作 | 验收标准 |
|---|---|---|
| D4-1 | `field_consents`（字段级同意）补迁移并启用 | GDPR/PIPL 粒度到字段 |
| D4-2 | `partners` / `partner_api_keys` 补迁移 | B2B 生态可部署 |
| D4-3 | 联邦 `sufficient_stats` 入口校验幂等键，重复提交返 409 | 重复 n-of-1 不污染聚合 |

---

## 7. 一个必须说破的判断

你现在有 **1669 个测试、0 失败、11 个 CI 工作流、JSON Schema、A2A 签名、E-value、联邦聚合**——**但一次全新部署连注册都过不去**。

这两件事之所以能同时成立，是因为：

> **测试建 schema 的路径（`create_all`）和生产建 schema 的路径（`alembic upgrade head`）从来没有人对齐过，而它们早已分叉 36 张表。**

D0 三天能做完。但它不是"补 37 个文件"的体力活——**它是把"楼是结实的"这个假设，从幻觉变成事实的唯一一步**。

在 D0 之前，我不建议再往上加任何新楼层。每加一层，都在给这条裂缝增加重量。

---

## 8. 本轮实测证据（可复现）

```bash
# 1. 迁移缺口
python - <<'EOF'
import re,io,glob
orm=set()
for f in glob.glob('app/models/*.py'):
    s=io.open(f,encoding='utf-8').read()
    orm|=set(re.findall(r'__tablename__\s*=\s*["\']([^"\']+)["\']', s))
mig=set()
for f in glob.glob('alembic/versions/*.py'):
    s=io.open(f,encoding='utf-8').read()
    mig|=set(re.findall(r'create_table\(\s*["\']([^"\']+)["\']', s))
print('ORM:',len(orm),'迁移:',len(mig),'缺:',len(orm-mig))
EOF
# → ORM: 61 迁移: 24 缺: 37

# 2. 空库 alembic
DATABASE_URL="sqlite+aiosqlite:///.../live.db" python -m alembic upgrade head
# → 建成 25 张（24 + alembic_version）

# 3. 实证部署崩溃
DATABASE_URL="sqlite+aiosqlite:///.../live.db" python -c "
from fastapi.testclient import TestClient; from app.main import app
c=TestClient(app)
r=c.post('/api/v1/auth/register', json={'email':'x@h.com','account':'x@h.com','password':'Str0ngPass!234'})
"
# → OperationalError: no such column: users.is_active

# 4. 迁移测试覆盖
grep -rl "alembic" tests/ | wc -l      # → 0
grep -c "alembic\|upgrade" .github/workflows/ci.yml   # → 0（仅匹配到无关注释）

# 5. 测试基线
pytest tests/ -q    # → 1669 passed, 2 skipped, 0 failed
```

**本轮对仓库的改动**：无源码改动。仅创建并清理了 `.aoci_probe/` 临时目录用于实证（已删除）。
