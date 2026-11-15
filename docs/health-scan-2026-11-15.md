# HealthLens 健康度扫描报告 · 2026-11-15

> 按《统一健康度扫描模板 v1》（`intel/_boards/健康度扫描模板-v1.md`）执行，固定 7 项。
> 扫描方式：只读核对，未改动项目代码；工作区 `C:\Users\xing\Desktop\所有项目\5.healthlens`。

---

### 1. Git 状态
- 分支 `main`，HEAD `602c65b1`（2026-11-11 docs: 刷新健康度扫描报告），领先 `origin/main` 8 个 commit，未推送。
- 工作树不干净：20 项变更（`M AGENTS.md` + 5 个 modified `data/` + 14 个 untracked `docs/intel`）。
- 最近 3 个 commit：`602c65b1`(11-11) → `6fab8c0e`(11-09 TRR-ALL sync) → `d49ac9fa`(11-08 README v0.40.0)。

### 2. CI 闸门
- 共 10 个 workflows（`ci.yml` + deploy/pages/docker/mcp/scheduled/uptime 等）。
- 实测真实退出码：`python tools/sync_version.py --check` → "OK: agent-card.json version == pyproject.version == 0.40.0"，**exit=0（真实绿）**；`--help` exit=1 属预期用法，非闸门失败。
- 通过/失败总数 **未核实**：本地缓存 `.workbuddy/cache/ci_logs/` 时间戳 1979-12-31 已失效，最近一次有效运行时间不可考。

### 3. 文档完备度
- 存在且较新：`README.md`✅（v0.40.0，18360B）、`AGENTS.md`✅（16049B）。
- 缺失：`ARCHITECTURE.md`❌、`PROJECT_VISION.md`❌、`docs/ARCHITECTURE.md`❌、`docs/README.md`❌。
- 诚实边界声明完整；README 声称 2048 测试函数、701 部古籍入库、四角色 Agent 团队，本次未逐一核验（标"未核实"）。

### 4. 数据/资产新鲜度
- `data/` 最新更新 2026-11-09；`knowledge/` 最新 `case_evidence_db.json` 更新 2026-10-16（距本次扫描 **29 天**）。
- 数据来源可追溯；`knowledge/` 数据疑似过期，是否需刷新待确认。

### 5. 未决问题
- 待修复标记：`app/`+`tests/` 下 TODO/FIXME/XXX 共 **22 处**；测试文件 108 个。
- 线上探测：`healthlens.io/` 200✅；`healthlens.io/api/v1/health` **404**⚠️；`lm203688.github.io/healthlens/` **404**⚠️。
- 阻塞项：GitHub token 授权未到位，20 项本地变更 + 8 个领先 commit 无法提交推送。

### 6. 能力边界自评
- 已完成（有证据）：P0 锚点核验 4/4✅；定位重构✅（诊断门控 inactive/fail-closed、三档精度、PRS AUC 0.6–0.7）。
- 未达成（如实标注）：真实人群数据验证❌（现全部 in-silico 合成数据）；线上 API 404❌；CI 有效日志❌。
- 与目标差距：核心科学验证（真实人群数据）与线上可访问性为当前最大短板。

### 7. 本周建议动作（≤3 项）
- **建议1：[P0] 修复线上 `/api/v1/health` 404 并确认部署** — 首页可访问但 API 与 GitHub Pages 404，直接影响用户信任与 Nadi 竞赛演示。
- **建议2：[P1] 用户授权后提交并推送 20 项本地变更** — 积压 8 个领先 commit 未推送，阻碍后续 CI 与多人协作。
- **建议3：[P1] 刷新 `knowledge/` 数据 + 补 CI 有效日志 + 核验 README 声明** — 数据 29 天未更新、CI 日志失效，需恢复可审计的闸门记录。

---

> 报告状态：已按 AGENTS.md 要求 `git add` 并 commit 归档。扫描时间 2026-11-15 09:08（Asia/Shanghai）。
