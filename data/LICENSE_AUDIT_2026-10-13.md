# HealthLens 知识平面许可审计 —— 公开发布（Zenodo DOI）前置阻断项核查

**审计日期**：2026-10-13
**审计触发**：《科学先进性与技术壁垒评估暨 SCI 就绪度报告 2026-10-12》§S2-4
「知识平面公开发布（Zenodo DOI + 方法学声明 + **许可审计：古籍语料可能含 AGPL/ODbL**）」
**审计原则**：只采信可核验证据（文件内声明 / GitHub API / git remote），找不到许可声明的一律如实标注 `unknown`，不推测、不代为定性。

---

## 0. 一句话结论

**当前 `knowledge/` 知识平面不可整包公开发布。** 阻断点单一且明确：古籍语料的**上游原始文本无任何许可证**（GitHub API `license: null`），而 HealthLens 的派生数据中内嵌了这些上游文本的**逐字摘录**（`source_quote` / `passage`）。

好消息是：仓库自身尚未对外发布（`MANIFEST.distribution` 全部为 `false`），本审计赶在发布前完成，属于可无损修正的时点。

---

## 1. 逐资产许可判定

| # | 资产 | 许可声明 | 可公开发布 | 证据 |
|---|---|---|---|---|
| 1 | 代码（`app/` `tools/` `healthlens_agent/` `mcp-server/`） | **MIT** | ✅ 可 | `LICENSE`（Copyright (c) 2026 Li Xing）；`mcp-server/LICENSE` |
| 2 | `data/tcm_mkg/`（6,207 条草药实体） | **MIT** | ✅ 可 | 文件内自述：`license: "MIT (repo code/data, Copyright (c) 2024 Zeng Jingqi)"`、`origin_repo: https://github.com/ZENGJingqi/GraphAI-for-TCM`、`zenodo_doi: 10.5281/zenodo.13763953` |
| 3 | `data/case_evidence_db.json`（29 证据案例 + 91 合成夹具） | MIT | ✅ 可 | 内容为 HealthLens 自撰案例摘要 + 文献**书目引用**（DOI/刊名），非受版权保护的文章全文转载；DOI 已逐条 Crossref 核验 |
| 4 | `data/engine_validation_metrics.json` + `validation_snapshots/` | MIT | ✅ 可 | HealthLens 自生成计算产物 |
| 5 | `data/axis_term_mapping.json` | MIT + **条件** | ⚠️ 条件可 | 仅使用 GB/T 20348-2026 术语**名称**（事实性成分，不受版权保护），未复制标准正文；已标 `gbt_confirmation_required=True` 待官方确认术语映射准确性 |
| 6 | `data/phenoage_alignment.json` / `app/core/phenoage.py` | MIT | ✅ 可 | 实现的是已发表学术公式（数学公式不受版权保护）；合成数据为自生成；引用 DOI 10.1371/journal.pmed.1002760 为书目引用 |
| 7 | `data/DOI_VERIFICATION_REPORT_2026-10-13.md` / `doi_verification_results.json` | MIT | ✅ 可 | Crossref 事实性元数据 + 自撰核验结论 |
| 8 | `knowledge/`（知识平面聚合） | 声明 **MIT** | ⚠️ 完整性缺失 | `knowledge/LICENSE` 为 MIT；但 `MANIFEST.integrity.sha256 = null`、`signed = false`，发布包完整性未建立 |
| 9 | **`data/tcm_structured/`（神农本草经 / 食疗本草）** | 派生部分 MIT；**上游 unknown** | ❌ **阻断** | 见 §2 |
| 10 | **`data/classical_slices.json`（613 条古籍切片）** | 派生部分 MIT；**上游 unknown** | ❌ **阻断** | 见 §2 |

---

## 2. 阻断项详解：古籍语料上游许可缺失

### 2.1 溯源链（实测，非推测）

```
data/tcm_structured/神农本草经.json
  └─ source_file: "000-神农本草经.txt"      ← 声明的上游原文
        └─ 位于 C:\Users\xing\Desktop\Qoder\小说\游医创世纪\中医\中医古籍txt合集\
              └─ git remote origin: https://github.com/xiaopangxia/TCM-Ancient-Books.git
                    └─ 702 文件 / 250MB / README 仅 56 字节
                          "TCM-Ancient-Books 中医药古籍文本，近700项"
```

### 2.2 上游许可状态的直接证据

| 核查动作 | 结果 |
|---|---|
| 上游仓库目录内 `LICENSE`/`许可` 文件 | **不存在** |
| GitHub API `GET /repos/xiaopangxia/TCM-Ancient-Books` → `license` 字段 | `null` |
| GitHub API `GET /repos/xiaopangxia/TCM-Ancient-Books/license` | **HTTP 404** |
| 上游 `README.md`（全 56 字节） | 无许可/授权/来源声明，仅标题与一句说明 |
| 上游仓库 commit 数 | 仅 3 个（Initial commit / add files / fix some files） |

**法律含义（如实陈述，不做法律意见）**：仓库未附带许可证时，著作权法默认授予作者「保留所有权利」，**不产生任何再分发授权**。这意味着把该合集内容（或其摘录）以 Zenodo 等渠道公开发布，在上游许可未澄清前缺乏授权基础。

### 2.3 为什么 HealthLens 的派生数据同样受阻

关键在于 HealthLens 的数据里**内嵌了上游文本的逐字摘录**：

| 文件 | 逐字摘录字段 | 条目数 |
|---|---|---|
| `data/tcm_structured/神农本草经.json` | `entities[].source_quote` | 全量 |
| `data/tcm_structured/食疗本草.json` | `entities[].source_quote` | 全量 |
| `data/classical_slices.json` | `slices[].passage` | 613 |

派生部分的 MIT 许可（`slice_id` / `axis_hint` / `matched_keywords` / 结构化 schema）不受影响，但**逐字摘录字段的权利仍属上游**。MIT 覆盖不了它覆盖不到的东西。

> **需要澄清的常见误判**：唐代/清代古籍原文本身因版权保护期早已届满，通常被视为公有领域。但公有领域的对象是**原文内容**，而 (a) 特定**辑校本**（如孙星衍辑本）的校勘工作、(b) 现代**录入与数字化**工作、(c) 聚合者的**汇编选择**，都可能构成新的受保护权利或附带独立许可条件。上游合集未声明许可，正是这三条都无法排除的证据。这也是 `knowledge/LICENSE` 自己在 §A5/B5 中写下的风险：
> *"Before redistributing internationally, review the source of each text for potential AGPL/ODbL contamination."*
> 本审计确认该风险**具体、可定位、真实存在**——不是假设。

### 2.4 时效性说明（对作者有利的一面）

`knowledge/MANIFEST.json` 的 `distribution` 字段显示：

```json
{ "local_embed": true, "cdn": false, "huggingface": false, "zenodo": false }
```

即**知识平面从未对外发布**，仅本地内嵌使用。本审计赶在 Zenodo 发布动作之前完成，因此阻断项是「尚未发生的合规风险」，而非「已发生的违规」——修正成本为零。

---

## 3. 修正方案（按成本从低到高）

### 方案 A —— 立即可执行（推荐，成本≈0）

**发布「脱敏变体」而非原始语料**：保留 HealthLens 自撰的派生结构，剥离上游逐字摘录字段。

已提供工具 `tools/redact_for_public_release.py`，生成 `data/publishable/` 下的可发布副本：
- 剥离 `data/classical_slices.json` 的 `slices[].passage`
- 剥离 `data/tcm_structured/*.json` 的 `entities[].source_quote`
- 在每份产物写入 `redaction_notice`，保留上游指针（repo URL + 文件号）供他人自查，但不搬运内容

**可发布性**：剥离后产物只含 HealthLens 自撰的 schema、ID、轴标注与关键词启发式结果，全部 MIT，可直接上 Zenodo。

### 方案 B —— 联系上游授权（成本：一封邮件）

向上游仓库维护者（`xiaopangxia`）发出明确的再分发许可请求（建议 CC-BY 或 ODbL 声明）。取得书面确认后，原始语料即可整包发布。这是唯一能保留逐字摘录的路径。

### 方案 C —— 更换公有领域语料源（成本：中）

改用明确声明公有领域/CC0 的替代古籍文本源重建 `tcm_structured/`，再重跑切片工具。可彻底消除上游依赖，但需重做抽取与校验。

---

## 4. 顺带发现的其他发布前置缺口

| 项 | 现状 | 建议 |
|---|---|---|
| `MANIFEST.integrity.sha256` | `null` | 发布包应生成内容哈希 |
| `MANIFEST.integrity.signed` | `false` | 发布包应签名 |
| `MANIFEST.distribution.zenodo` | `false` | 待 Zenodo 上传后置 `true` 并记录 DOI |
| `GB/T 20348-2026` 术语 | `gbt_confirmation_required=True` | 国标正文受 SAC 版权保护；当前仅引用术语名称（事实），发布说明中应如此陈述，不得暗示已获国标文本授权 |
| `.env` 曾含过期 `APP_VERSION=0.9.0` | 已修正（2026-10-13） | 与许可无关，但提示发布前需复查 `.env.example` 中的过期值（已清） |

---

## 5. 审计结论

- **可直接发布**：代码全量、`tcm_mkg/`、`case_evidence_db.json`、验证快照、PhenoAge 对标产物、DOI 核验报告、四向映射表 —— 第 1、2、3、4、5、6、7 项。
- **必须修正后发布**：`data/classical_slices.json`、`data/tcm_structured/` —— 第 9、10 项（走方案 A）。
- **建议补强**：`knowledge/` 完整性签名与 MANIFEST 发布状态位 —— 第 8 项。

**本轮处置**：按方案 A 生成脱敏可发布副本（`tools/redact_for_public_release.py` → `data/publishable/`），并在工具与产物内显式记录上游指针与剥离范围。方案 B/C 作为后续选项留待作者决策，未擅自联系上游、未擅自替换语料源。

---

*本审计仅陈述可核验的许可事实与法律含义的常规理解，不构成法律意见。正式发布前建议由具备资质的法务复核。*
