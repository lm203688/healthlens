# HealthLens Zenodo 数据发布清单（S2-4）

> 目标：把案例库、映射表、验证快照、DOI 核验结果、因果装置基准
> 打包为 Zenodo 数据集，产出**可一键上传**的 manifest。
> 用户只需 Zenodo 账号 + 一次点击。

## Zenodo 上传前置

1. 注册 Zenodo 账号（GitHub OAuth 即可）：https://zenodo.org/
2. 获取 API Token：https://zenodo.org/settings/user-tokens
   （推荐创建专用 token，权限最小化）
3. 确认发布许可：**CC BY 4.0**（本项目默认）

## 上传清单（manifest.json）

见 `submissions/zenodo/deposit_manifest.json`。可直接用作
`zenodo-cli` 或 REST API 上传的元数据文件。

## 待上传文件清单

| 文件                                          | 大小      | 用途                |
| --------------------------------------------- | --------- | ------------------- |
| `data/case_evidence_db.json`                  | ~250 KB   | 29 真证据 + 91 合成 |
| `data/axis_term_mapping.json`                 | ~150 KB   | 四向映射表          |
| `data/classical_slices.json`                  | ~400 KB   | 613 条古籍切片      |
| `data/doi_verification_results.json`          | ~30 KB    | DOI 核验结果        |
| `config/axes/axes.yaml`                       | ~15 KB    | 八轴阈值外置配置    |
| `validation_snapshots/BASELINE.json`          | ~2 KB     | 计算验证基线        |
| `HealthLens_论文_计算验证_补充数据.csv`       | ~50 KB    | 论文补充数据        |
| `HealthLens_论文_框架概念图_Figure1.svg`      | ~30 KB    | 论文主图            |

**总计**：~925 KB。远低于 Zenodo 单文件 50 GB 限制。

## 数据发布元数据

```yaml
title: "Integrated Steady-State Axis Framework: Evidence Database & Cross-Modal Mapping"
doi_namespace: "10.5281"
publisher: "Zenodo"
publication_year: 2026
resource_type:
  type: "Dataset"
  subtype: "Database"

creators:
  - name: "HealthLens Research Team"
    affiliation: "HealthLens (open-source)"
    # ORCID to be filled at upload time

description: |
  Evidence database (120 entries: 29 with verified DOIs, 91 synthetic
  validation fixtures) and cross-modal terminology mapping for the
  eight-axis integrated steady-state framework (A-H). Includes:
  
  - Case evidence database with per-entry DOI verification status
  - Four-way terminology mapping: GB/T 20348 <-> axes <-> pathways <-> classical texts
  - 613 classical Chinese medicine text fragments with axis annotations
  - Eight-axis threshold configuration (externalized)
  - Validation baseline snapshot for reproducibility
  
  All upstream bibliographic fields have been audited via
  three independent fail-loud defenses against leakage.

subjects:
  - Medicine
  - Health Science
  - Traditional Medicine
  - Bioinformatics
  - Public Health

keywords:
  - integrative medicine
  - traditional Chinese medicine
  - computational wellness
  - structural causal model
  - pharmacogenomics
  - evidence verification
  - data residency
  - jurisdiction-aware compliance

license: "CC-BY-4.0"

related_identifiers:
  - identifier: "https://github.com/HealthLens/healthlens"
    relation: "isSupplementTo"
    scheme: "URL"

access_right: "open"
```

## 一键上传命令（用户手动）

```bash
# 使用 Zenodo REST API v2（推荐）
curl -X POST https://zenodo.org/api/deposit/deposits \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  -H "Content-Type: application/json" \
  -d @submissions/zenodo/deposit_payload.json

# 上传文件（逐个）
for f in data/case_evidence_db.json \
         data/axis_term_mapping.json \
         data/classical_slices.json \
         data/doi_verification_results.json \
         config/axes/axes.yaml \
         validation_snapshots/BASELINE.json \
         HealthLens_论文_计算验证_补充数据.csv \
         HealthLens_论文_框架概念图_Figure1.svg; do
  curl -X POST https://zenodo.org/api/deposit/deposits/$DEPOSIT_ID/files/$(basename $f) \
    -H "Authorization: Bearer $ZENODO_TOKEN" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @"$f"
done

# 发布（生成 DOI）
curl -X POST https://zenodo.org/api/deposit/deposits/$DEPOSIT_ID/actions/publish \
  -H "Authorization: Bearer $ZENODO_TOKEN"
```

## 发布后回填

1. 从 Zenido 页面复制 DOI（形如 `10.5281/zenodo.12345678`）
2. 回填到：
   - `submissions/medrxiv/submission_manifest.json` → `data_availability.doi`
   - `submissions/medrxiv/data_availability_statement.md` → 顶部 DOI 行
   - `HealthLens_论文_英文版_全文.md` → Data Availability 段
   - `CHANGELOG.md` → 本次发布说明
3. 用 `curl -I https://doi.org/10.5281/zenodo.XXXXXXX` 验证可解析

## 未闭合（诚实）

- **需要真实 Zenodo 账号**：AI 无法自动注册与授权
- **需要 ORCID**：manifest 里 `creator.orcid` 保留占位符 `PENDING_USER_FILL`
- **发布时机由用户决定**：本包只提供材料，不代替用户的学术判断
