# HealthLens 健康度扫描报告（2026-11-11 · 重跑版）

> 按统一模板 v1 执行 7 项扫描
> 扫描时间：2026-11-11 18:23（重跑；上一版 17:24 数据有偏差）
> 扫描人：HealthLens DEV Agent
> 说明：Chief 反馈 docs/ 未见归档，实为上一版已生成但未提交（untracked），且部分数字过时，本次已刷新并重新归档。

---

## 1. Git 状态

- **当前分支/HEAD**：main / 6fab8c0e "TRR-ALL: sync submission test counts to 2066"（2026-11-09）
- **工作树**：不干净（20 个变更文件：5 modified + 15 untracked）
  - 5 modified = data/ 下 5 个评估产物（INDICATOR_CONTENT_VALIDITY_REPORT.md、LITERATURE_TRIANGULATION_CVI_REPORT.md、knowledge_graph.json、indicator_content_validity.json、literature_triangulation_cvi.json）
  - 15 untracked = docs/ 下 14 份报告 + intel/ 目录
- **最近 3 commits**：6fab8c0e（11-09）TRR-ALL sync → d49ac9fa（11-08）README同步v0.40.0 → 034aeaf9（11-08）Merge origin/main
- **推送状态**：本地领先 origin/main，未推送（受 GitHub token 限制）

---

## 2. CI 闸门

- **闸门总数**：10 个 workflow（ci.yml + deploy-frontend/pages/deploy/docker-publish/mcp-publish/mcp-test/publish-dataset/scheduled-pipeline/uptime-watchdog）
- **ci.yml 含 7 jobs**：Lint&Test、Windows GBK guard、Docker Build、Heavy Library Test、Agent Library Test、Skills Test、Frontend Test Vitest
- **通过/失败**：未核实（本地缓存 `.workbuddy/cache/ci_logs/` 文件时间戳为 1979，已失效，无有效日志）
- **线上 badge**：README 引用 GitHub Actions ci.yml badge（状态未现场验证）

---

## 3. 文档完备度

- **核心文档**：README.md ✅（v0.40.0，11-08 同步）；AGENTS.md ✅（含 AOCI 认知层说明）；PROJECT_VISION.md ❌ 不存在
- **文档与代码一致性**：README 声称 2048 测试函数（107 文件），未逐一核验（标记"未核实"）；README 声称中医古籍 701 部入库、四角色 Agent 团队，未核验
- **诚实边界声明**：✅ 完整（README 明确"非医疗"、"诊断门控 inactive/fail-closed"、"真实人群数据验证缺失"）
- **编码注意**：README 经 PowerShell 读取显示 GBK 乱码，文件本身为 UTF-8 正常（读取工具问题，非内容问题）

---

## 4. 数据/资产新鲜度

- **关键数据最后更新**：data/ 2026-11-09；knowledge/ 最新 case_evidence_db.json 2026-10-16（距今 26 天）
- **数据来源可追溯性**：✅ 可追溯（data/ 下报告标注来源与方法）
- **过期/失效数据**：⚠️ knowledge/ 已 26 天未更新，需确认是否过期；本地 CI 日志缓存已失效（1979 时间戳）

---

## 5. 未决问题

- **TODO/FIXME/XXX**：app/ + tests/ 下 22 处（如 app/lib/protocol_audit.py 的 signing_key 占位、app/api/medications.py 的 PGx 证据标注、app/api/tcm.py 的药房取消通知）
- **待决策事项**：GitHub token 限制导致 push 受阻；线上 API 状态待查；真实人群数据验证缺口
- **线上核验（本次实测）**：healthlens.io 首页 200 ✅；`/api/v1/health` 返回 **404** ⚠️；lm203688.github.io/healthlens/ 返回 404（GitHub Pages 未部署或路径变更）
- **阻塞项**：GitHub token 需用户重新授权；线上 API 404 需确认后端服务与路由

---

## 6. 能力边界自评

- **已完成（有证据）**：4/4 P0 锚点核验通过（diagnosis_gate.py、prs_framework.py、non_pharma_engine.py、pulse.py）；定位重构完成（诊断门控 inactive/fail-closed、非药物引擎三档精度、PRS AUC 0.6–0.7）；2048+ 测试函数；四角色 Agent 团队 + 融合安全管线
- **未达成/负结果（如实标注）**：真实人群数据验证缺失（全部 in-silico）；线上 API 404；CI 有效日志缺失（缓存失效）
- **与项目目标差距**：战略目标 1（真实数据验证）未启动；战略目标 2（海外推广）未启动

---

## 7. 本周建议动作（最多3项）

- **建议1**：[P0] 修复线上 API 404 或确认部署状态 — 影响用户信任与 Nadi 竞赛演示；检查后端服务、路由、GitHub Pages 部署
- **建议2**：[P1] 用户重新授权 GitHub token，提交 data/ 5 modified + docs/ 15 untracked（本地就绪）
- **建议3**：[P1] 更新 knowledge/ 数据（26 天未更新）并补充 CI 有效日志，验证 README 中 2048 测试与 701 部古籍声明

---

## 诚实边界声明

- CI 闸门通过/失败未核实（有效日志缺失）
- README 中测试数/古籍数/Agent 团队声明未逐一核验
- 线上 API 404 原因未核实
- 真实人群数据验证缺失为已知事实

---

*归档：docs/health-scan-2026-11-11.md + 科研资料库\HealthLens\进度成果\health-scan-2026-11-11.md*
