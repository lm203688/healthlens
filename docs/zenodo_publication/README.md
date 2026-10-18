# Zenodo 数据集打包说明

**版本**：v0.1.0-draft · 2026-10-16
**目标平台**：Zenodo · `https://zenodo.org/`
**DOI 占位**：`10.5281/zenodo.<DATASET_ID_PLACEHOLDER>`
**用途**：把 HealthLens 公开数据打包成可发布的 Zenodo deposit

> 参考：`submissions/zenodo/deposit_manifest.json`、`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6 与 §8 阶段 E。
> **本说明不实际调用 Zenodo API**——所有字段与文件清单在此处准备，实际上传需研究者使用个人 Zenodo 账号 + API token。

---

## 1. 打包结构

本数据集包含 3 个核心子集：

### 1.1 rubric_benchmark（评估基准）
- 文件：`data/rubric_benchmark_v1.json`
- 用途：LLM judge 与人类专家一致性评估的 rubric 基线
- 用途章节：白皮书 §评估体系

### 1.2 knowledge_graph_redacted（脱敏知识图谱）
- 文件：`data/graphrag/redacted/*.json`（占位路径，具体以 `tools/redact_for_public_release.py` 输出为准）
- 用途：八轴↔TCM↔通路↔经典医籍的脱敏术语映射
- 覆盖：`data/axis_term_mapping.json`、`data/classical_slices.json`

### 1.3 case_evidence_verified（案例证据库 · 已验证部分）
- 文件：`data/case_evidence_db.json`（`citation_status ∈ {verified, verified_crossref, traditional}`）
- 用途：Agent 个性化推荐的证据来源
- 覆盖率：**诚实报告**（见 §3）

## 2. 打包执行步骤

> **注意**：以下步骤需研究者本地手动执行；本仓库**不自动上传 Zenodo**。

### Step 1：准备 manifest
```bash
cd C:/Users/xing/Desktop/healthlens
python tools/redact_for_public_release.py            # 生成脱敏数据
ls -la data/graphrag/redacted/ data/rubric_benchmark_v1.json data/case_evidence_db.json
```

### Step 2：创建 Zenodo deposit
```bash
# 1) 到 https://zenodo.org/settings/user-tokens 创建 API token
# 2) 使用 submissions/zenodo/deposit_manifest.json 的 metadata 段
# 3) POST https://zenodo.org/api/deposit/deposits with metadata
# 4) POST https://zenodo.org/api/deposit/deposits/{id}/files/{filename} with each file
# 5) POST https://zenodo.org/api/deposit/deposits/{id}/actions/publish to generate DOI
```

### Step 3：回填 DOI
- 把 Zenodo 返回的 `10.5281/zenodo.<id>` 填入：
  - `submissions/medrxiv/data_availability_statement.md`
  - `submissions/s3-2/` 相关文件
  - `docs/prospective_cohort/osf_preprint_draft.md` §1 URL 占位
  - `HealthLens_论文_投稿版.docx`

## 3. 数据集清单

详细字段见 `dataset_manifest.json`。核心子集概览：

| 子集 | 主文件 | 记录数 | 许可 | 引用格式 |
|---|---|---|---|---|
| rubric_benchmark | `data/rubric_benchmark_v1.json` | 60 条 rubric | CC-BY 4.0 | 见 `CITATION.cff` |
| knowledge_graph_redacted | `data/graphrag/redacted/*.json` | 依赖脱敏输出 | CC-BY 4.0 | 见 `CITATION.cff` |
| case_evidence_verified | `data/case_evidence_db.json` | 见 §3.3 覆盖率 | CC-BY 4.0 | 见 `CITATION.cff` |

### 3.1 覆盖率统计（诚实披露）

以 `data/case_evidence_db_report_2026-10-16.md` 为准。截至 2026-10-16：
- **总案例数**：120
- **verified_crossref（本轮新增）**：7
- **verified（先前 Crossref 核验通过）**：6
- **hallucination_resolved（1 条幻觉已修正）**：1
- **broken_citation**：1（原 `10.1016/j.ther.2026.105127` 未解析）
- **traditional**（古籍/食疗，无 DOI）：8
- **unverified_no_publication**（无匹配文献）：14
- **synthetic_validation**（自动生成验证夹具）：91
- **合计 verified**：约 14/120 = **11.7%**（诚实值，远低于报告 §10 #5 的 95% 目标）

**披露原因**：报告 §10 #5 目标 95% 在当前混合 schema（29 真实文献 + 91 验证夹具）下不可诚实达成；已明确分区，待后续真实回填纵向数据后再做覆盖率统计。

## 4. 引用格式

参见 `CITATION.cff`。示例（BibTeX）：

```bibtex
@dataset{healthlens_zenodo_2026,
  title       = {HealthLens Integrated Steady-State Axis Framework: Evidence Database and Cross-Modal Mapping},
  author      = {HealthLens Research Team},
  year        = {2026},
  doi         = {10.5281/zenodo.<DATASET_ID_PLACEHOLDER>},
  publisher   = {Zenodo},
  license     = {CC-BY-4.0},
  url         = {https://doi.org/10.5281/zenodo.<DATASET_ID_PLACEHOLDER>}
}
```

## 5. 使用政策

参见 `COMMUNITY_USE_POLICY.md`。核心条款：
- **CC-BY 4.0**：允许商业与非商业使用，须署名；
- **学术引用要求**：引用时须同时引用数据集 DOI 与 `app/lib/nof_one_effect.py` 的代码 DOI（若已发布）；
- **不承诺医疗**：本数据集不用于临床诊断或治疗决策；
- **抽取攻击声明**：公开前的抽取攻击评估由 L4 团队执行，见 `graphrag_publication_checklist.md`。

## 6. 版本与关联

- 与 `submissions/zenodo/deposit_manifest.json` 的关系：本目录为**说明文档**（人类可读），`submissions/zenodo/deposit_manifest.json` 为**机器可读**的元数据模板。
- 与 `docs/zenodo_publication/graphrag_publication_checklist.md` 的关系：发布前检查清单，须全部勾选后方可提交 Zenodo。

## 7. 版本历史

- v0.1.0-draft（2026-10-16）：初稿，等待 Zenodo 账号 + API token 后上传

---

**wellness 声明**：本数据集为 wellness 研究领域开放数据，非医疗数据集。使用者不得将其用于临床决策。
