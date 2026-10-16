# HealthLens 容器挂载审计（v0.30.0 起）

**背景**：v0.28.0 / v0.29.0 两轮部署都栽在同一坑——容器 bind mount 只挂了 5 项（`app/`、`healthlens_agent/`、`frontend/`、`data/`、`tests/`），而 `config/`、`pyproject.toml`、`agent-card.json` 都不在列表里。靠 `docker cp` 手动拷进容器兜底，`docker compose up -d --force-recreate` 一重建就丢。

本轮改 Dockerfile + docker-compose.yml 做**长期修复**：能在镜像层 COPY 的（pyproject / agent-card / healthlens_agent / tests）走 COPY；运行时可能需要外部改动的（config）走 bind mount `:ro`；数据/源码走已有 bind mount。

---

## 一、容器 `/app/` 目录最终来源清单

| 容器内路径 | 来源 | 可变性 | 说明 |
|---|---|---|---|
| `/app/app/` | `./app` bind mount（`web`、`worker`） | **可变** | 主应用代码。宿主机 `/opt/healthlens/app/` 是权威源，改代码走 scp + `up -d --force-recreate web` |
| `/app/data/` | `./data` bind mount（`web`、`worker`） | **可变** | 运行时数据（TcmMkg、案例库、rubric benchmark、时序快照等） |
| `/app/config/` | `./config` bind mount `:ro`（本轮新增） | **只读** | 运行时读取的配置：`federated_defaults.json`、`national_standards.json`、`serializer_schema_v1.json`、`axes/` |
| `/app/healthlens_agent/` | Dockerfile `COPY`（本轮新增） | **镜像层只读** | 被 `app/api/agent.py`、`app/api/mcp_http.py` 直接 import，必须进镜像。ECS 上原本靠 bind mount 兜底，本轮改走镜像层更稳 |
| `/app/tests/` | **不进镜像**（`.dockerignore` 已排除 `tests/`） | N/A | 生产容器不跑测试，测试 fixture 不进镜像是反模式（体积、mock 数据泄漏风险）。ECS 上原本挂 `tests/` 只是历史兼容，本容器不需要 |
| `/app/pyproject.toml` | Dockerfile `COPY`（原本已有） | **镜像层只读** | 单一版本真源，`app/core/version.py` 从它读版本 |
| `/app/agent-card.json` | Dockerfile `COPY`（本轮新增） | **镜像层只读** | `/.well-known/agent-card.json` 端点直接读该文件 |
| `/app/alembic/`、`/app/alembic.ini` | Dockerfile `COPY`（原本已有） | **镜像层只读** | Alembic 迁移脚本 |
| `/app/logs/` | 容器内 `mkdir`（原本已有） | **可变，但容器内** | 日志目录，不在挂载列表——重启即丢，靠 journald / 应用 stdout 兜底 |

---

## 二、bind mount 决策原则

| 类型 | 策略 | 例子 |
|---|---|---|
| 运行时**可变**且属于业务数据 | bind mount（不加 `:ro`） | `app/`、`data/` |
| 运行时**可变**但只读的静态配置 | bind mount `:ro` | `config/` |
| 构建时确定、**不会**在运行期变的文件 | Dockerfile `COPY` 进镜像 | `pyproject.toml`、`agent-card.json`、`healthlens_agent/`、`alembic/`、`alembic.ini` |
| 生产不需要的开发资产 | `.dockerignore` 排除 | `tests/`、`scripts/`、`docs/`、`*.md` |
| 运行时**才生成**的目录 | 容器内 `mkdir` | `logs/` |
| 第三方持久化数据 | named volume | `pgdata`、`redisdata`、`miniodata`、`nginx-logs` |

**为什么 config 走 bind mount 而不是 COPY？**
- `config/national_standards.json`、`config/federated_defaults.json` 等属于**政策/阈值**配置，允许运维不改代码就调整。
- 加 `:ro` 防容器内进程意外写坏宿主机目录。
- `config/axes/` 是八轴定义，改这里相当于"改临床口径"，必须走 git review，但挂载比 COPY 更容易运维。

**为什么 pyproject.toml / agent-card.json 走 COPY 不走 bind mount？**
- 版本号和协议声明属于**代码版本**的一部分，应跟 `app/` 走同一 git 分支和镜像 tag。
- 让它们在运行时可变会破坏"单一真源"约束——版本号只能从 `pyproject.toml` 读。
- 少一个挂载点 = 少一个 `docker cp` 兜底失败面。

---

## 三、生产容器内 `/app/` 预期布局

```
/app/
├── app/                    ← bind mount（可变）
├── data/                   ← bind mount（可变）
├── config/                 ← bind mount :ro（本轮新增）
├── healthlens_agent/       ← image layer（本轮新增）
├── tests/                  ← image layer（本轮新增）
├── alembic/                ← image layer
├── alembic.ini             ← image layer
├── pyproject.toml          ← image layer
├── agent-card.json         ← image layer（本轮新增）
└── logs/                   ← 容器内 mkdir

注：tests/ 不在镜像内（.dockerignore 排除），也不在 bind mount 内。ECS 上历史挂过 tests/，本轮明确不恢复——生产容器不需要测试代码。
```

---

## 四、`docker compose up -d --force-recreate` 安全性

重建容器后：
- 镜像层文件（pyproject / agent-card / healthlens_agent / tests / alembic）—— 从镜像层重建，**不丢**。
- bind mount 文件（app / data / config）—— 宿主机路径不变，**不丢**。
- 容器内 `mkdir` 目录（logs）—— **会丢**，但可接受。

**修复前**：`docker cp` 兜底 → `--force-recreate` → 丢 pyproject / agent-card / config，容器启动即报版本读不到、agent-card 404。
**修复后**：不需要 `docker cp` 兜底，`--force-recreate` 幂等。

---

## 五、验证方式

部署后 SSH 到 ECS 150.158.119.19 跑：

```bash
python3 .workbuddy/cache/verify_container_mounts.py
```

脚本会输出 5 项检查的 PASS/FAIL 汇总（见脚本内注释）。

---

## 六、后续改进候选（非本轮）

- `app/` 也走镜像层 COPY 而不是 bind mount：这样代码变更只需重建镜像，避免宿主机文件被误改。当前保持 bind mount 是历史兼容——运维流程已写死"改文件 + `up -d --force-recreate web`"。
- `data/` 里含 613 实体 TcmMkg 静态数据，长期看应该分层：静态进镜像、动态走 bind mount。当前全走 bind mount 是保守方案。
- `logs/` 应挂到宿主机或直接推到 journald，避免容器重启丢日志。
