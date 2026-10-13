# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.26.2] - 2026-10-13

### Added（S3 工程化落地 + 公开发布合规处置）

**S3-1 A2A Agent Card（智能体发现层）**
- `agent-card.json`（仓库根，10132B < Google Cloud Agent Registry 10KB 上限）：A2A v1.0 格式，8 个 REQUIRED 字段齐备（name/description/version/supportedInterfaces/capabilities/defaultInputModes/defaultOutputModes/skills），11 个 skill
- `GET /.well-known/agent-card.json` 发现端点（A2A 规范服务位置）：运行时以 `pyproject.toml` 为单一真源注入版本，卡片版本与运行时版本不可能漂移；`Cache-Control: public, max-age=300`；HEAD 与 GET 共用同一次序列化的 body，保证二者 `content-length` 一致（内容寻址缓存不会把 HEAD 当旁路）
- **诚实性边界**：`conformanceNote` 如实声明本服务**未实现 A2A 任务生命周期操作**（SendMessage / GetTask / CancelTask），实际可编程接口为 MCP JSON-RPC 2.0，通过 `capabilities.extensions` 指向规范 URI 显式声明；未支持的能力（streaming / pushNotifications / extendedAgentCard）一律显式置 `false`，不省略
- `tests/test_agent_card.py`：**25 用例**，含 fail-loud 断言「每个 skill 的 interfaceUrl 必须对应 OpenAPI 真实路由（模板路径按段占位匹配）」，锁死「在卡片里编造端点夸大能力」这类虚假声明
- 兼容性修复：Starlette >=1.6 不再自动为 GET 路由补 HEAD，故 `HEAD` 需显式声明（`include_in_schema=False`，HEAD 无独立契约不进 OpenAPI）；修复过程中发现并修掉一处 `request` 未标注被 FastAPI 误判为必填查询参数的 422

**S3-5 单一版本真源 + 构建垃圾清理**
- 根因：`.env` 第 3 行 `APP_VERSION=0.9.0`（8/28 残留）+ `.env.example` 0.8.2 使 `Settings.APP_VERSION` 实测为 0.9.0，与 `pyproject.toml` 的 0.26.1 不符——版本号可被环境变量静默覆盖
- 处置：移除 `.env` / `.env.example` 中的 `APP_VERSION`，改为版本不可被 env 覆盖；`app/core/version.py` 从 `pyproject.toml [project].version` 读取（Python 3.9 兼容：`tomllib` + `tomli` 回退）
- `GET /api/v1/version` 端点 + `tests/core/test_version.py`（7 用例）
- `auto-pipeline/dist_build*` / `dist_prev_*` 11 个历史构建目录删除（26M → 5.4M），删除前备份至 `Desktop/_healthlens_dist_backup_2026-10-13`

**S2-4 上游知识平面许可审计（公开发布阻断项）**
- `data/LICENSE_AUDIT_2026-10-13.md`：逐条核对上游语料许可。核心结论——GitHub 仓库无 LICENSE 文件时默认「保留所有权利」（all rights reserved），**公有领域 ≠ 已许可**；`TCM-Ancient-Books` 经 GitHub API 确认 `license: null`，属公开发布合规阻断
- `tools/redact_for_public_release.py`：剥离 `source_quote` / `passage` / `efficacy` / `citation` 等原文承载字段，产物写入 `data/publishable/` + `REDACTION_MANIFEST.json`；支持 `--check` / `--keep-verbatim` / `--strip-bibliographic`
- 三方案（A 脱敏 / B 最小可用 / C 私有部署）已给出可执行路径，实际发布（Zenodo DOI 注册等）需用户决策

### Fixed

- **S2-4 脱敏泄漏（严重，已修复并推送）**：首版工具 `STRIP_MAP` 只配了 `["passage", "efficacy"]`，
  漏掉同样承载上游逐字引文的 `citation` 字段——60/613 条切片、995 字符（《太平御览》《大观》等
  原文引文）随 `data/publishable/classical_slices.json` 一起推上了公开仓库（commit `49f80ea0de`）。
  更严重的是**上一版 CHANGELOG 与本条目曾声称已剥离 `citation`，属虚假声明**——声明覆盖了实际行为。
- **根因（比漏配更值得记）**：`_emit` 的校验只按 `STRIP_MAP` 自身核对「声明剥离的字段是否消失」，
  配置漏项时校验必然通过。自证校验器无法发现配置本身的缺口，这是这类缺陷静默上生产的通用机制。
- **修复：三道 fail-loud 防线**
  1. 配置驱动（原有）：STRIP_MAP 声明剥离的字段必须真的消失；
  2. **独立黑名单** `UPSTREAM_VERBATIM_FIELDS`（不依赖 STRIP_MAP）：任何上游逐字字段残留在产物中即中断；
  3. 空转检测：STRIP_MAP 配置了但源中不存在的字段记入 `inert_fields`（告警不中断——空转不等于泄漏，
     且黑名单是跨来源并集，断言中断曾误伤引用其它来源字段的情形）。
- **`AUTHORIZED_RETENTION` 授权保留通道**：逐字字段要么被剥离、要么显式授权保留，二者都不沾即中断。
  `--keep-verbatim` 只把 `efficacy` 加进该集合（需上游书面授权）。集合只能收敛于黑名单内，
  试图豁免自撰字段（如 `slice_id`）会被断言拦下——防止它退化成绕过黑名单的后门。
- **产物自我声明**：`redaction_notice` 新增 `authorized_retention` / `retained_bibliographic` /
  `retained_bibliographic_rationale`。保留书目字段（book/author/dynasty/entity/entity_type/property，
  短事实性元数据）时**必须在产物里写明保留理由**，不得伪装成「已剥离」；新增 `--strip-bibliographic`
  最保守模式供上游明确要求时使用。
- **`tools/gh_api_push.py` 凭据发现失效**：原逻辑只查 `healthlens/.git/config`（该目录已删），
  现补 `ROOT/.git/config` 与 `~/.git-credentials` 回退，并把凭据正则由 `[^@]+` 收紧为 `[^@\s]+`。
- **自写统计 bug**：`verbatim_chars_removed` 原在已剥离的产物记录上统计，恒为 0（自称报告移除量却永远
  报 0）；改为按源记录统计，并新增 `verbatim_chars_by_field` 逐字段明细。
- **换行符导致报告字节数不可信**：`redacted_bytes` 按 LF 序列化文本统计，但 `Path.write_text()` 在
  Windows 上把 `\n` 转成 `\r\n`，实测 `classical_slices.json` 落盘 326,488 字节而报告 314,705，
  差值恰为 11,783 个 CRLF——「省 36.8%」这一统计随之不可信。改为二进制写盘强制 LF（JSON 产物跨平台
  惯例），并加 fail-loud 断言 `落盘字节 == redacted_bytes`；新增 2 个回归用例锁住「报告字节等于落盘
  字节」与「产物无 CRLF / 无 BOM」两条不变式。修复后三份产物落盘字节与清单报告值逐个精确相等。
- **`tests/tools/test_redact_for_public_release.py`：18 用例**，含
  **字段处置完整性**校验——源数据每个字段必须明确归入 剥离 / 经复核保留 / HealthLens 自撰 三者之一，
  新增未分类字段即失败（这正是拦住 `citation` 的那条：它当时属于「无人认领」）；
  以及**事故复现**用例（把 STRIP_MAP 改回当年错误配置必须被拦下）、授权集合边界、CLI 接线、
  源文件只读不变、记录数不丢、notice 声明自洽。
- 脱敏实测：源 `citation` 非空 60 条 / 995 字符 → 产物 **0 条 / 0 字符**；四类逐字字段全部清零，
  613 条记录无丢失；`leaked_fields_total=0`；741,785 → 388,705 字节。

### Changed
- `pyproject.toml`：0.26.1 → 0.26.2（单一真源）；`agent-card.json` 静态版本同步

### Verified
- 三套测试合计 **461 passed, 0 failed**：`tests/` 397 + `healthlens_agent/tests/` 58 + `edge/healthgateway/tests/` 6

## [0.26.1] - 2026-10-13

### Added（《科学先进性与技术壁垒评估暨 SCI 就绪度报告 2026-10-12》硬阻断项清零续篇）

**S1-2 跨轴归一化（消除「弱项判定被输入完整度驱动」）**
- `app/core/axis_scorers.py`：八轴统一 `_finalize()`，score = 100 − 100 × (Σ实际扣分 / Σ可用输入最大扣分)；`AxisScore` 新增 `penalty_ratio` 审计字段
- 实证修复：旧公式下同一异常态「1 项全异常=72 分 vs 5 项全异常=0 分」（少填看起来更健康）；新公式下同质异常恒同分，score<70 ⟺ ratio>0.3 在八轴间等价
- 诚实边界（实测证伪「与数量完全无关」后修正文档）：可用输入很少时分数被可测量部分主导（prorated scoring 语义），论文中须作方法学约定明示
- `tests/core/test_axis_scorers.py` +5 验收用例；全量 `409 passed, 0 failed`

**S1-3 H 轴对标 PhenoAge（文献时钟对标装置）**
- `app/core/phenoage.py`：忠实实现已发表 PhenoAge 公式（Liu 2018 PLoS Med；公式订正 DOI 10.1371/journal.pmed.1002760），SI 单位纪律（临床单位入口自动换算），fail-loud（缺项/CRP≤0 不编造）
- 公式正确性锚点：40 岁人群均值 SI 输入 → xb=-9.3615 → PhenoAge=40.3（与手算一致）；健康 25 岁 → 17.0；同岁不健康 → 73.1
- `tools/phenoage_alignment.py` → `data/phenoage_alignment.json/.md` + 散点 SVG：n=200 合成画像，PhenoAge 偏移 vs HealthLens 生物学年龄偏移 Pearson r=0.806 / Spearman ρ=0.812；**明示合成装置验证、共享输入仅 glucose+CRP、真实队列校准为后续工作**
- `tests/core/test_phenoage.py`：7 锚点用例

**S1-6 claims 引擎测试 + 策略缺口修复**
- `tests/lib/test_claims_engine.py`：8 用例（五法域加载、未知法域 fail-closed 回落 EU、US 禁 diagnosis 词/CN 不禁、US 屏蔽 icd_code/CN 放行、端点开关差异、免责声明、审计非阻塞）
- **修复真实缺口**：`claims_policy/cn.yaml` 补 `general` 默认免责声明——此前 CN 是五法域中唯一缺失 general 的策略，无诊断/风险/pgx 内容的输出完全拿不到免责声明，与「非医疗」红线不一致

**S1-7 Benchmark 去自指涉**
- `healthlens_agent/benchmark.py`：维度评分分级标注——可测维度（工程落地 78、安全合规 92）改用 probe 实测公式，不可测维度保留定性自评但 `measured=False`，输出 note 明示「不得对外声称为测量结果」

### Fixed
- **B4**：英文论文 `HealthLens_论文_英文版_全文.md` 结论段「ten axes」→「eight axes（A–H；I/J reserved）」，中/英/代码/勘误四处轴数口径一致
- **B3**：CASE-029 刊名错标订正——`10.1186/s12967-026-08038-9` 原标 J Nanobiotechnology，Crossref 核验实为 Journal of Translational Medicine（s12967 为该刊前缀；J Nanobiotechnol 前缀为 s12951）；`data/` + `knowledge/evidence/` 两副本 + 生成 md 同步，订正说明入库
- `tools/gen_case_evidence_md.py`：CASE-006 勘误从硬编码改为数据驱动（`citation_note` 字段透出）

### Verified（本轮实测复核，前序工作确认有效）
- B1 八轴运行期：`score_all_axes()` 八轴全返回不抛异常（N1 已修）
- B2 计算验证：`tools/engine_validation.py` 重跑与 `validation_snapshots/BASELINE.json` **完全一致**（7.7 / 0.95 / 154 / L1=134 / 0.697），论文数字=CI 数字
- B5 E/G 解耦：axes.yaml 分层阈值（E 30/20 vs G 25/15）+ 实测仅 HRV 输入 E≠G（hrv=18: 88 vs 91）
- 全量测试 **409 passed, 0 failed**（历史 31 failed 全部清零）

## [0.26.0] - 2026-10-13

### Added（阶段 B：技术壁垒深挖 S0–S1 实施）

**S0-5 / S1-1 DOI 证据核验（学术/B2B 一票否决项止血）**
- `tools/verify_evidence_dois.py`：Crossref REST 逐条解析案例库全部 DOI，诚实标注 `verified` / `hallucination_resolved` / `unverified_text` / `traditional` / `broken_citation` / `synthetic_validation` / `unsourced`
- 订正 AI 幻觉引用 `10.1038/s41591-026-04102-8`（臆造 "Kirkland AFFIRM"，L1 最高证据位）→ 真实 Farr 2024 `10.1038/s41591-024-03096-2`；CASE-006 事实字段同步改为 60 名绝经后女性骨代谢、结论克制无过度宣称
- 标记 CASE-030 死链 `10.1016/j.ther.2026.105127`（HTTP 404）为 `broken_citation`
- 产物：`data/doi_verification_results.json`、`data/DOI_VERIFICATION_REPORT_2026-10-13.md`；每案写入 `citation_status`/`doi_verified`/`doi`/`source_canonical`
- 如实说明：案例库 29 条真证据 + 91 条合成校验夹具，「≥95% DOI 覆盖」当前数据上不可达，不编造 DOI

**S1-2 四向映射表（国标国际化）**
- `tools/build_axis_term_mapping.py` → `data/axis_term_mapping.json/.md`：GB/T 20348-2026 术语（中英，`gbt_confirmation_required=True` 待官方确认）↔ 八轴(A–H) ↔ 38 通路 ↔ 古籍（真实数据推导）

**S1-3 古籍原文切片 + 八轴标注**
- `tools/build_classical_slices.py` → `data/classical_slices.json/.md`：**613 条**切片（真实 `source_quote`，来源可溯源，远超 ≥100 目标），八轴关键词启发式标注（`keyword_heuristic_v1`），每条 `needs_expert_review=true`（非权威，须专家复核；已知局限：本草多「杀邪辟恶」致 F 偏多、「络脉」罕见致 C 偏少）

**S2-1 因果推断引擎 + 端点（wellness_simulator 因果化）**
- `app/lib/causal_simulator.py`：SCM 结构 / 反事实 / 桥接敏感度 / 校准 / bootstrap / E-value（公开 API: `scm_structure` / `counterfactual` / `bridge_sensitivity` / `calibrate` / `causal_report` / `derive_baseline` / `simulate`）
- `app/api/causal.py` + 注册：`/api/v1/causal/{scm,sensitivity,levers}`（公开）+ `{counterfactual,calibrate,report}`（需登录），fail-loud 400（未知轴/未知杠杆/越界分）
- `tests/api/test_causal.py`：11 用例（含鉴权 + 越界 400）；全量 `389 passed, 0 failed`；已推送 commit `c239cb2`

**S3-4 频率处方引擎**
- `app/services/frequency_prescription.py` + `app/api/frequency.py`（`GET /tracks`、`POST /prescribe`）

### Changed
- `data/case_evidence_db.json` meta v1.3：legend 10 轴(A–J) → **8 轴(A–H)** + reserved I/J，与代码/用例对齐（S0-6）；`knowledge/evidence/` 副本同步
- `tools/gen_case_evidence_md.py`：跳过 HL- 夹具、兼容 string source、输出 CASE-006 勘误
- 论文 `HealthLens_论文_英文版_全文.md`、`Figure1.svg`：十轴→八轴

### Removed
- 删除嵌套重复子树 `healthlens/`（30 文件，本地备份 `Desktop/_healthlens_removed_2026-10-13/`；远端 Contents API DELETE 同步，commit `9da05be`）

## [0.25.0] - 2026-10-10

### Added（阶段 A：国际化重评估 P0 落地）

**A3 管辖感知 Claims 引擎**（核心）
- `app/lib/claims_engine.py`：策略加载+缓存、21 类字段别名映射、端点级开关、敏感词扫描、按法域附加免责声明、审计留痕。fail-closed：未知法域回落 EU（最严）
- `claims_policy/cn.yaml` / `us_fda.yaml` / `uk_mhra.yaml` / `au_tga.yaml` / `eu_mdr.yaml`：五法域策略文件
- 已接入端点：`/diagnosis/analyze`、`/diagnosis/results`、`/diagnosis/results/{id}`、`/genome/pgx`

**A4 区域数据驻留代码级约束**
- `app/models/user.py`：新增 `region` / `jurisdiction` 字段（默认 cn）
- `alembic/versions/006_add_region_jurisdiction.py`：迁移 + 2 个索引
- `app/lib/region_guard.py`：`X-HL-Region` 请求头 → 环境变量 → 默认区域三级优先级；`enforce_region_match()` 强制拦截跨区域读写 PII

**A2 八轴参数外置（YAML + jurisdiction 维度）**
- `config/axes/axes.yaml`：8 轴 × 6+ 指标 × 5+ 阈值，支持法域覆盖
- `app/lib/axis_config.py`：加载器（`get_thresholds` / `get_threshold` / `get_axis_config`），缓存 + 硬编码 fallback

**A1 知识/数据平面分离骨架**
- `knowledge/`：`README.md` / `__init__.py` / `loader.py` / `MANIFEST.json` / `LICENSE`
- `KnowledgeLoader`：零 FastAPI 依赖，只读文件系统，向后兼容退化到 `data/`
- 资产清单：evidence 120 条 / pathways 38 条 / tcm_entities 613 条 / axis_config v1.0

### Changed

**A5 数据质量清理**
- `data/case_evidence_db.json` v1.3：清理 4 条 I 轴残留（CASE-024/025/026/029），加"已清理"note
- `data/pathway_to_syndrome_map.json`：59→**38** 通路，删除 21 个单字符/垃圾键
- 全仓轴数统一为 A-H 八轴（消除 I/J 论文漂移）

**A6 PGx 输出合规**
- `app/api/genome.py::/pgx` 接入 Claims 引擎；EU/US/UK 下 `pgx_pathogenic_grading=false` 返回 403 而非降级放行；CN 保留完整功能

### Security（合规）
- Wellness 边界从**文案纪律**升级为**代码策略**：字段过滤 + 端点级开关 + 按法域定制免责声明
- 遵循伊利诺伊州《Wellness and Oversight for Psychological Resources Act》(2025-08-01)：免责声明不再作为合规手段
- 未知法域 fail-closed 回落 EU（最严），跨区域读写 PII 直接 403

### Dependencies
- 新增 `pyyaml>=6.0`（Claims 引擎策略加载 + 八轴阈值加载）

### Version Unification
- `pyproject.toml` / `app/config.py` APP_VERSION / `mcp-server/server.json` / `PRINCIPLES.md` / `README.md` 同步到 **v0.25.0**

## [0.24.0] - 2026-10-09

### Changed (P0-4：伪 China-PAR 替换为"自评风险量表"表述)
- `app/core/risk_engine.py`：`ASCVDRiskEngine` / `DiabetesRiskEngine` 改名为**自评量表**（透明启发式，非 China-PAR/CDRS Cox 系数与 S0(t)），`MetabolicSyndromeEngine` 保留 CDS 五项真实阈值
- `RiskAssessmentResult` 新增 `disclaimer` 字段；`risk_type` 从 `"ascvd"`/`"diabetes"` 改为 `"ascvd_self_assess"`/`"diabetes_self_assess"`（`metabolic_syndrome` 保持不变）
- `assess_all()` 返回字典 key 同步改为 `ascvd_self_assess`/`diabetes_self_assess`/`metabolic_syndrome`
- `app/api/dashboard.py` `POST /risk-assessment` 响应新增全局 `disclaimer` 字段与每条 assessment 的 `references`/`disclaimer`，避免前端把倾向百分比误读为 10 年 ASCVD 概率
- `healthlens_agent/mcp_server.py` `hl_risk_assess` 描述改为自评量表口径，返回体带 `risk_type`/`references`/`disclaimer`
- 文档同步改口径：`README.md`、`CHANGELOG.md`、`docs/HealthLens_产品技术白皮书.md`、`healthlens/README.md`、`healthlens/CHANGELOG.md` — 全部去掉"China-PAR 模型""10 年心血管事件概率"表述
- 测试同步：`tests/core/test_risk_engine.py`、`tests/api/test_dashboard.py` 更新 `risk_type` 断言

### Security (合规)
- 对外表述统一为"自评风险量表"（`self_assessment_scale`），禁止再宣称"China-PAR 模型""10 年 ASCVD 风险预测"（P0-4 验收标准）
- 自评倾向百分比明确标注为**无量纲 0-100 指数**（非概率），disclaimer 明确"不构成诊断或治疗建议"

## [0.2.0-mcp] - 2026-09-24

### Added
- **HealthLens MCP Server (v0.2)**: 分层 MCP Server，安全默认暴露 L1+L2（无个人数据），L3（个性化）需 `HL_MCP_EXPOSE_PRIVATE=1` 环境变量
- **6 个 L1+L2 公开 tool**：`hl_health_check`、`hl_search_knowledge`、`hl_get_axis_detail`、`hl_get_wellness_article`、`hl_suggest_general_diet`、`hl_suggest_general_motion`
- **4 个 L3 私有 tool**（默认关闭）：`hl_fusion_engine`、`hl_risk_assess`、`hl_tcm_constitution`、`hl_evidence_grade`
- **MCP 分发元数据**：`mcp-server/server.json`（Registry schema）、`README.md`（安装+使用）、`.mcp.json`（客户端配置模板）、`LICENSE`、`test_install.sh`（验证脚本）
- **设计文档**：`docs/healthlens-mcp-design.md`（分层策略、数据边界、GDPR 影响、部署方案、注册市场清单）
- **上架指南**：`docs/mcp-marketplace-submission.md`（Glama/Registry/Smithery/mcp.so/PulseMCP 提交步骤 + 监控指标 + 回滚方案）
- **CLI 支持**：`python -m healthlens_agent mcp --demo / --jsonrpc / --tools`（JSON-RPC stdio fallback）
- **GDPR 免责声明**：每个 tool 描述嵌入 "not medical advice" 声明

### Changed
- `healthlens_agent/__main__.py`：转发 `mcp` 子命令参数给 `mcp_server`
- `healthlens_agent/mcp_server.py`：从扁平 tool 列表重构为分层注册表（L1/L2/L3）

### Security
- L1+L2 默认暴露，L3 关闭（`HL_MCP_EXPOSE_PRIVATE=0`）
- 每个 tool 明确标注数据边界（"No personal data" / "GDPR Art. 9"）
- 红线清单：checkin 记录、账号密码、中医处方判定、诊断输出永不通过 MCP 暴露

## [0.8.2] - 2026-07-20

### Added
- **RBAC 权限系统**: RoleChecker 依赖注入, require_doctor/require_admin/require_doctor_or_admin
- **处方管理**: POST/GET/GET{id}/PUT{id} 4 个 API 端点, RX 编号自动生成
- **TesseractOCR 引擎**: 完整的 pytesseract + pdf2image 实现
- **Token 加密**: Fernet 对称加密 OAuth access_token (cryptography)
- **安全启动校验**: 非 DEBUG 模式检测不安全密钥直接 SystemExit(1)
- **角色管理 API**: PUT /auth/role (仅 admin), seed_admin.py 种子脚本
- **Celery Worker 健康检查**: docker-compose.yml + docker-compose.prod.yml
- **Prometheus 监控**: /metrics 端点, RequestMetricsMiddleware (请求计数/延迟/路径归一化)
- **Docker 生产部署**: .dockerignore, 多阶段构建 (pyproject.toml), ENTRYPOINT+CMD 分离
- **Nginx 反向代理**: HTTPS 准备, 速率限制 10r/s, 安全头, 50M 上传限制
- **CI/CD 流水线**: GitHub Actions ci.yml (lint+test+build) + deploy.yml (tag 触发+自动回滚)
- **ECS 部署脚本**: --dev/--rollback 模式, Redis 正确检查, 轮询健康检查, pg_dump 备份
- **docker-compose.prod.yml**: 资源限制, 内网端口隔离, Redis 密码认证, Nginx 服务

### Fixed
- **xiaomi 连接器名称**: "xiaomi" -> "xiaomi_health" (ALLOWED_SOURCE_TYPES 与注册名称不匹配导致同步永远失败)
- **诊断审核权限**: 移除 user_id 过滤, 医生可审核所有患者诊断 (非仅自己)
- **Alembic 迁移不可用**: env.py 未导入 settings, DATABASE_URL 为空; 修复为自动从 settings 回填
- **requirements.txt 不同步**: 缺 cryptography/pytesseract/prometheus-client, 19 个包无版本约束; 全部补齐
- **分页一致性**: records/connections/genome 列表端点补齐 page/page_size/total/total_pages
- **Celery SessionLocal**: 空引用 -> 惰性工厂 (避免 SQLite 开发环境导入 psycopg2)
- **CORS 安全**: 硬编码 ["*"] -> settings.CORS_ORIGINS 可配置
- **Dashboard**: diagnosis_name AttributeError -> diagnosis_text
- **版本号统一**: pyproject.toml/config.py/.env 全部对齐 v0.8.2
- **MINIO_BUCKET**: .env.production MINIO_BUCKET_NAME -> MINIO_BUCKET (与 config.py 一致)

### Changed
- **依赖**: pyproject.toml 新增 cryptography/pytesseract/pdf2image/paddleocr/paddlepaddle/prometheus-client
- **Dockerfile**: requirements.txt -> pyproject.toml, 补全 OCR 系统库 (tesseract/libgl)
- **reports.py**: 分析报告解析返回完整指标列表 (含正常项)
- **health_analyzer**: risk_factors 区分 high/borderline 级别, 基于异常数量分级建议
- **observations**: stats 端点返回 std_dev/cv_percent/by_category

### Security
- Token 加密存储 (Fernet, SHA256 of JWT_SECRET_KEY)
- 生产环境不安全密钥拒绝启动
- RBAC 权限控制 (patient/doctor/admin 三级)
- CORS 可配置 (生产环境禁止通配符)
- Redis 密码认证 (docker-compose.prod.yml)
- Nginx 安全头 (X-Frame-Options, X-Content-Type-Options, HSTS)
- 资源限制防 OOM (CPU/Memory limits)

## [0.7.0] - 2026-07-18

### Added
- FastAPI 应用骨架 (14 路由模块, 21 数据库表)
- 西医诊断流程: 上传 -> OCR -> 异常检测 -> ICD-11 诊断 -> 处方推荐 -> FHIR 导出
- 中医辨证流程: 体质问卷 (9 种) -> AI 辨证 -> 方剂推荐 -> 配送订单 (状态机)
- 慢病风险自评量表: ASCVD（自评，非 China-PAR）+ 糖尿病（自评，非 CDRS）+ 代谢综合征（CDS 五项真实阈值）
- 健康管理: 目标 -> 进度 -> 依从性 -> 仪表盘
- 报告解析器: 22 种中英文体检指标正则匹配
- TCM 方剂库: 15 味中药, 方剂搜索引擎
- 数据连接器: 华为健康/Apple Health/Withings/小米/医院 LIS (Phase 1 Mock)
- Celery 异步任务: OCR/分析/诊断
- 通知服务: 数据库持久化

[0.7.0]: https://github.com/your-org/healthlens/releases/tag/v0.7.0
[0.8.2]: https://github.com/your-org/healthlens/releases/tag/v0.8.2
