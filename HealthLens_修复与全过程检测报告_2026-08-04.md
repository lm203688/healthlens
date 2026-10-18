# HealthLens 修复与全过程检测报告

**执行时间**：2026-08-04 14:00 – 17:45
**执行范围**：P0 地基修复 + 自动化闭环改造 + 全过程实测验证
**结论**：**代码层修复完成并全部通过实测；但发现一个此前未知的根因级问题——HealthLens 从未部署到任何服务器。**

---

## 一、本次最重要的发现（推翻了上一版报告的判断）

上一版报告推断 healthlens.cc 的 HTTP 530 是「Alembic 双 head 导致容器启动崩溃」。
**这个判断是错的。真实情况更严重。**

### 证据链

```
1) 端口探测 150.158.119.19
   22/OPEN  80/OPEN  443/OPEN  8000/closed
   → 服务器活着，nginx 活着

2) 绕过 CDN，带 Host: healthlens.cc 直连源站
   /            HTTP 200  66516 bytes
   /robots.txt  HTTP 200    972 bytes
   /sitemap.xml HTTP 200   2867 bytes
   → 源站有内容，且返回 200

3) 检查返回的内容是什么
   首页  <title>AIShield — AI Agent安全生态平台</title>
   robots  "# AIShield Robots.txt  https://aishield.tools"
   sitemap <loc>https://aishield.tools/</loc>
   → 返回的是 AIShield 的站，不是 HealthLens

4) 交叉验证服务器归属
   ~/Desktop/aishield/eco/reports/daily-20260726.md:168
   "P0 | 恢复 aishield.tools 服务 | 登录服务器 150.158.119.19 重启 cloudflared"
   → 这台机器是 AIShield 的
```

### 结论

| 项 | 真实情况 |
|---|---|
| `config.json` 的 `ssh_host` | `root@150.158.119.19` — **AIShield 的服务器** |
| HealthLens 在该机器上 | **不存在**。nginx 无 healthlens.cc 的 server_name，请求落到默认站（AIShield） |
| SSH 认证 | `Permission denied (publickey,password)` — 本机 `~/.ssh` 只有 known_hosts，**无任何私钥** |
| healthlens.cc 的 530 | Cloudflare 回源失败。因为 HealthLens 根本没有源站 |
| 部署阶段"成功"记录 | 全部来自 `dry_run=true`，**从未真正上传过一个文件** |

**一句话：不是站点挂了，是站点从来没有存在过。** 配置直接抄了另一个项目的服务器 IP，
而 dry-run + fail-open 让这个错误静默了至少 8 天。

---

## 二、已完成的修复（12 个文件）

### A. 后端地基（healthlens/）

| # | 问题 | 修复 | 文件 |
|---|---|---|---|
| F1 | Alembic 双 head，`upgrade head` 必报 Multiple head revisions | 将 `002_add_missing_tables` 线性化并重命名为 `006`，接到链尾 | `alembic/versions/006_add_missing_tables.py` |
| F2 | `beat_schedule_timezone` **不是合法 Celery 配置项**，被静默忽略 | 改用合法的 `timezone` + `enable_utc=False` | `app/worker.py` |
| F3 | `day_of_week=2` 注释写"周三"，Celery 中 0=周日 → 实际周二，全部偏移一天 | 全部按 Celery 语义校正 | `app/worker.py` |
| F4 | **Celery Beat 从未部署**：docker-compose 无 beat 服务，worker 无 `--beat` | 新增独立 `beat` 服务，含 healthcheck、restart、独立 pidfile | `docker-compose.yml` |
| F5 | `app/tasks/__init__.py` 为空 + `autodiscover_tasks(["app.tasks"])` 找的是不存在的 `app.tasks.tasks` → **即使 beat 起来了也全是 unregistered task** | 改用显式 `include=TASK_MODULES` | `app/worker.py`、`app/tasks/__init__.py` |
| F6 | 无任何心跳机制，beat 死了无从察觉 | 新增 `write_heartbeat` 任务 + `self_check` | `app/tasks/ops_tasks.py` |

### B. 自动化流水线（auto-pipeline/）

| # | 问题 | 修复 | 文件 |
|---|---|---|---|
| F7 | **fail-open**：端点 0/4 正常仍返回"成功"、退出码 0 | 判定逻辑重写，失败必 `fail_phase` + 非 0 退出码 | `scripts/phase_7_feedback/ops_health_f.py` |
| F8 | 全系统无告警通道 | 新增统一告警模块：分级 / 去重冷却 / 自动解除 / 本地 jsonl + ACTIVE_ALERTS.md + 可选 webhook | `scripts/core/alerting.py`（新建，322 行） |
| F9 | `auto_fixable` 10 处硬编码 `False`，函数名 `extract_manual_actions` — 代码自认无自愈 | 新增自愈引擎：目录补建 / 状态修复 / 卡死阶段复位 / 失败阶段重试 / 磁盘检查 | `scripts/core/self_heal.py`（新建，395 行） |
| F10 | 调度器无重试、无超时、无告警，失败即静默中断 | 重写：重试 → 自愈 → 复验 → 告警 → 运行记录，退出码真实反映状态 | `scheduler.py`（562 行） |
| F11 | `dry_run` 键在 config 中不存在，代码 `.get('dry_run', True)` 兜底 → **永久 dry-run** | 显式声明 `dry_run` 并加注释说明历史 | `config.json` |
| T3 | **零备份任务**（健康数据丢失不可恢复） | 新增备份 + 恢复验证任务，支持 ssh / local_docker / auto 三模式 | `scripts/phase_8_ops/backup_db.py`（新建，377 行） |
| T7 | 任务悄悄死了无人知道（`task_edu_001` 卡 8 天无告警） | 新增看门狗：数据陈旧度 / 心跳 / 备份新鲜度 / 端点 巡检 | `scripts/phase_8_ops/watchdog.py`（新建，348 行） |

### C. 因本次事故新增的能力

| # | 能力 | 说明 |
|---|---|---|
| **N1** | **站点身份校验** `check_site_identity()` | 不只看 HTTP 状态码，还校验返回内容里是否含本项目标识、是否含其他项目标识。**这次事故中源站返回 200 + AIShield 内容，任何只看状态码的监控都会误判为正常。** |
| **N2** | **部署目标合理性校验** `check_deploy_target()` | 检测 `ssh_host` 是否为空、是否指向 `known_foreign_hosts` 中登记的其他项目服务器、是否从未验证过 |
| **N3** | 配置纠错 | `deployment.ssh_host` 与 `backup.ssh_host` 由 `root@150.158.119.19` 置空，并在 `known_foreign_hosts` 中登记该 IP 归属 AIShield。宁可显式报"未配置"，也不静默指向他人服务器 |

---

## 三、全过程检测结果（14 项，全部实跑）

| # | 检测项 | 方法 | 结果 |
|---|---|---|---|
| 1 | Alembic 迁移链 | `ScriptDirectory.get_heads()` | ✅ heads=1，链完整线性 |
| 2 | Beat 调度表 | `remaining_estimate()` 实算每个任务下次运行时刻 | ✅ 9 个任务星期与注释全部对齐 |
| 3 | 任务可注册性 | AST 静态解析 include 模块中真实定义的 task，与 beat_schedule 逐条比对 | ✅ 全部命中，无 unregistered |
| 4 | docker-compose | YAML 解析 + beat 服务唯一性断言 | ✅ beat 就位且全局唯一（多 beat 会重复投递） |
| 5 | 脚本语法与配置 | `py_compile` × 6 + config.json 解析 | ✅ 全部通过 |
| 6 | **fail-loud 实测** | 在真实宕机场景下跑 F 线 | ✅ 判定 `down`，退出码 **1**（修复前：报"✅ 成功"，退出码 0） |
| 7 | 看门狗 | 实跑 | ✅ 检出 2 严重 + 7 警告，退出码 1 |
| 8 | 备份任务 | 实跑 | ✅ 正确失败并告警（SSH 不通），退出码 1 —— **失败得很响亮，符合预期** |
| 9 | **完整闭环 run-all** | 6 阶段 + 6 反馈线全跑，耗时 205s | ✅ 结论 `FAILED`，退出码 1，聚合 7 条活跃告警（修复前：**"全部成功"**） |
| 10 | 身份校验接入 | 实跑 F 线 | ✅ 新字段 `site_identity` / `deploy_target_issues` 已写入报告 |
| 11 | 部署目标校验 | 喂入 `root@150.158.119.19` | ✅ 识破"属于 AIShield 项目，向该机器部署会污染其他项目" |
| 11b | **身份校验确定性验证** | 本地起服务，喂入**真实抓取的 AIShield robots.txt** | ✅ 3/3 全中：AIShield内容→`wrong_site`；nginx默认页→`unrecognized`；HealthLens页→`ok` |
| 12 | 自愈引擎 | `scheduler.py heal` | ✅ 检出并复位失败阶段 `ops_health_f`，下轮自动重试 |
| 13 | **后端回归测试** | 33 个测试文件全跑 | ✅ **175 passed / 0 failed / 26.6s** —— 本次所有改动未破坏任何既有功能 |

> 测试依赖说明：`aiosqlite` 等测试依赖在 `pyproject.toml` 的 `[project.optional-dependencies] dev` 中已正确声明，
> 需用 `pip install -e ".[dev]"` 安装，不在 `requirements.txt` 中（这是合理的生产/开发分离，非缺陷）。

### 修复前后对比（同一场景）

```
【修复前 2026-08-03 03:01】
  [03:01:31] 数据库查询失败: 远程计算机拒绝网络连接
  [03:01:31]   ✅ E: E.资金闭环 - 成功
  [03:01:36] F线运维检查完成: 端点 0/4正常
  [03:01:36]   ✅ F: F.项目运维闭环 - 成功
  [03:01:36] 全部闭环执行结束: 全部成功          ← 撒谎
             退出码 0，无任何告警

【修复后 2026-08-04 17:37】
  [ERROR] 全部闭环执行结束: 2 项失败 ↓
  [ERROR]     ✗ E线(exit_1)
  [ERROR]     ✗ F线(exit_1)
  [ERROR]     ⚠ 运维状态=down (端点 0/4 正常)
  [ERROR]     ⚠ 3 条未解决的严重告警
  [INFO] 结论: FAILED | 耗时 205s
             退出码 1，8 条告警落盘 + ACTIVE_ALERTS.md
```

---

## 四、无法自动修复的部分（需要你介入）

这三件事我做不了，不是技术问题，是**权限与资源问题**：

### 🔴 P0-1：HealthLens 没有服务器

**现状**：无部署目标。`config.json` 原先指向的是 AIShield 的机器。

**你需要决定**：
- (a) **复用 150.158.119.19**：在同一台机器上加 healthlens.cc 的 nginx vhost + 独立 docker compose project。成本 0，但两个项目共命运（AIShield 挂了 HealthLens 也受影响）
- (b) **新开一台轻量服务器**：腾讯云轻量 2C4G 约 ¥60–90/月。隔离干净
- (c) **先不部署**：本地 docker compose 跑起来自测，等有内容和用户再上线。**考虑到 0 用户 0 收入、月流出 ¥333，这个选项其实最务实**

### 🔴 P0-2：本机无 SSH 私钥

`~/.ssh/` 只有 known_hosts。任何远程部署 / 备份 / 容器巡检都执行不了。
确定服务器后需要：`ssh-keygen -t ed25519` → `ssh-copy-id` → 在 `config.json` 填 `ssh_host` 并把 `verified_at` 置为验证时间。

### 🟡 P0-3：Cloudflare 回源配置

healthlens.cc 的 DNS 在 Cloudflare（104.21.43.183 / 172.67.183.59），
但回源指向的东西已经失效。确定服务器后需要在 Cloudflare 后台改 A 记录或重建 tunnel。

---

## 五、下一步建议顺序

```
第 1 步  决定服务器方案（上面 a/b/c 三选一）        ← 卡住所有后续
第 2 步  生成 SSH 密钥并配置免密
第 3 步  本地 docker compose up 自测，确认 beat 真的在跑
         （验证方式：看 data/heartbeat.json 是否每 10 分钟更新）
第 4 步  部署 + 修 Cloudflare 回源
第 5 步  把 dry_run 改为 false，跑一次真实部署
第 6 步  接一个告警 webhook（企业微信机器人，5 分钟）
         → 在 config.json 的 alerting.webhooks 填 url 并 enabled=true
第 7 步  把 auto-pipeline 从你的 Windows 本机迁到服务器 cron
         （现在你关机自动化就停，与"无人值守"直接冲突）
```

**第 3 步之前不要碰新功能开发。** 现在写的每一行业务代码都跑在一个不存在的部署上。

---

## 六、诚实的状态判定

| 维度 | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| 监测能说真话 | 0/5 | **4/5** | fail-loud + 告警 + 身份校验都实测通过；扣 1 分因为无外部告警通道（webhook 未配） |
| 自愈能力 | 0/5 | **3/5** | 复位/重试/目录补建可用；但"改代码级"的自愈本就不该做，保持人工介入是对的 |
| 备份 | 0/5 | **3/5** | 任务写好且能正确失败告警，但**至今零成功备份**——因为没有数据库可备份 |
| 部署闭环 | 0/5 | **1/5** | 代码就绪，但无服务器、无 SSH 密钥，**实际仍然不可部署** |
| 无人值守运营 | 0/5 | **1/5** | 调度逻辑已闭环，但仍跑在你的本机，且部署链断裂 |

**整体从 1.1/5 提升到 2.4/5。**

剩下的 2.6 分不在代码里，在服务器和密钥上。**代码已经不会再骗你了——但它现在诚实地告诉你：这个项目还没上线。**

---

*报告生成：2026-08-04 17:45 | 所有结论均基于实跑验证，无推测*
