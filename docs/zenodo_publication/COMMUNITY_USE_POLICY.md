# 社区使用政策

**版本**：v0.1.0-draft · 2026-10-16
**许可**：CC-BY 4.0（含署名与非医疗声明）
**平台**：Zenodo · `https://doi.org/10.5281/zenodo.<DATASET_ID_PLACEHOLDER>`

> 参考：`docs/zenodo_publication/README.md`、`submissions/zenodo/deposit_manifest.json`。
> 本政策与 `CITATION.cff` 中的 `preferred-citation` 段配合使用。

---

## 1. 许可

- 数据集许可：**Creative Commons Attribution 4.0 International (CC-BY 4.0)**
- 许可链接：https://creativecommons.org/licenses/by/4.0/legalcode
- 允许：
  - 商业与非商业使用
  - 修改、分发、再许可
- 条件：
  - **署名**：必须正确署名
  - **相同方式共享**：**不强制**（CC-BY 4.0 非 SA 变体）
- 保留权利：
  - 原作者保留其署名权
  - 我们保留撤回本政策中错误陈述的权利，但已下载副本仍按本政策执行

## 2. 学术引用要求

**任何引用本数据集的学术论文、研究报告、政策建议、媒体报道或产品文档，必须同时包含以下两项引用：**

### 2.1 数据集 DOI（必需）
```
DOI: 10.5281/zenodo.<DATASET_ID_PLACEHOLDER>
```

### 2.2 代码仓库 DOI（推荐）
```
https://github.com/HealthLens/healthlens
```

### 2.3 推荐 BibTeX 格式

```bibtex
@dataset{healthlens_zenodo_2026,
  title       = {HealthLens Integrated Steady-State Axis Framework: Evidence Database and Cross-Modal Mapping},
  author      = {HealthLens Research Team},
  year        = {2026},
  doi         = {10.5281/zenodo.<DATASET_ID_PLACEHOLDER>},
  publisher   = {Zenodo},
  license     = {CC-BY-4.0},
  url         = {https://doi.org/10.5281/zenodo.<DATASET_ID_PLACEHOLDER>},
  note        = {Wellness research dataset; not for clinical decision-making}
}
```

### 2.4 中文场景

中文出版物应保留上述 DOI 字段，并附一句中文说明：
> "本数据集为 wellness 研究用途，不用于临床决策。"

## 3. 使用范围

### 3.1 允许使用
- 学术研究与方法学复现
- 开源软件集成与评测
- 政策建议与健康经济学分析
- 教科书、教程与培训课程
- 商业 wellness 产品评测（须署名）

### 3.2 禁止使用
- **临床诊断或治疗决策**（wellness 定位，非医疗数据集）
- **个体化医疗建议**生成
- **保险核保**、**招聘筛查**、**教育考试**等非健康研究场景
- **军事、执法、国家安全**用途
- 与数据集作者或其研究资助方的**商业竞争**用途（须事前书面告知）

### 3.3 二次分发
- 二次分发本数据集时，必须在**分发位置**保留：
  - 本政策的完整链接
  - 原始数据集的 DOI
  - 原始署名
- 允许衍生数据集（derived dataset），但衍生数据集须**独立**发布新 DOI，不得声称是原始数据集的官方延伸。

## 4. 学术诚信

- 引用本数据集的论文**必须**：
  - 明确说明使用了本数据集的哪些子集；
  - 披露是否修改了字段、子集或数据；
  - 若修改了字段，需同时发布修改后的数据（可挂在本数据集的 related_identifiers 下）。
- **不允许**：
  - 声称本数据集**未包含**的字段或结论；
  - 修改 `citation_status` 字段以夸大证据覆盖率；
  - 移除或替换本政策与许可声明。

## 5. 合规责任

### 5.1 使用者责任
- 使用者**自行**评估其在所在法域的数据使用合规性；
- 中国境内使用须遵守：PIPL、DSL、GB/T 35273-2020、GB/T 22239-2019；
- 欧盟/英国使用须遵守：GDPR Art.6/7/9，健康数据二次使用需**明确同意**；
- 其他法域（US/UK/AU/JP/KR）按当地法规评估。

### 5.2 提供方免责
- 我们**不担保**数据集的准确性、完整性或特定用途适用性；
- 我们**不承担**因使用本数据集导致的任何临床或商业损害；
- 我们**不授权**本政策覆盖的例外，除非另有书面协议。

## 6. 抽取攻击声明

本数据集的 GraphRAG 组件（`data/graphrag/redacted/`、`data/axis_term_mapping.json`、`data/classical_slices.json`）在公开发布前会经过抽取攻击评估（extraction attack assessment），见 `graphrag_publication_checklist.md`。

- 使用者**不得**尝试通过 prompt-injection、taxonomy-traversal、embedding-leakage 等手段从本数据集获取未公开的结构化知识；
- 若发现公开数据泄露了未公开内容，请通过 `security@healthlens.example`（占位）报告。

## 7. 变更日志

- v0.1.0-draft（2026-10-16）：初稿，等待 Zenodo 上传后定稿

---

**wellness 声明**：本政策不修改数据集的 wellness 研究定位；任何将本数据集用于临床决策的行为均违反本政策第 3.2 条。
