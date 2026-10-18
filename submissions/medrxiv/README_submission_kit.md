# HealthLens medRxiv 投稿包（S2-3）

> 目标：把「整合医学稳态轴框架 + 因果推演装置 + 合规解释层」的核心贡献，
> 组织成 medRxiv 可接受的 preprint 提交格式。**这是交接包，不是自动投稿**——
> medRxiv 需要用户账号 + 机构邮箱审核，AI 无法自动完成最后一击。

## 目录结构

```
submissions/medrxiv/
├── README_submission_kit.md         本文件——操作步骤与检查清单
├── submission_manifest.json         投稿元数据（作者/摘要/资助/冲突利益）
├── data_availability_statement.md   数据可用性声明（Zenodo DOI 占位）
├── ethics_and_consents.md           伦理声明模板
├── cover_letter_to_medrxiv.md       投稿信（可直接编辑后上传）
└── reviewer_guidance.md             审稿人导向说明（可选）
```

## 前置条件（用户手动完成）

1. **注册 medRxiv 账号**：https://www.medrxiv.org/about/submit
   - 首选机构邮箱（学术/科研/医疗机构）
   - 若为独立研究，需至少 1 位 co-author 使用机构邮箱
2. **获取 ORCID**：https://orcid.org/register（每位作者都要有）
3. **准备 Zenodo DOI**（见 `submissions/zenodo/` 目录）
4. **确认稿件语言**：默认英文（medRxiv 主用）；英文版全文见
   `HealthLens_论文_英文版_全文.md`

## medRxiv 提交字段对照

| medRxiv 字段          | 本包对应来源                                        |
| --------------------- | --------------------------------------------------- |
| Title                 | 论文正文 H1                                         |
| Abstract              | 论文正文 Abstract 段落                              |
| Subject Area          | `Medicine > Epidemiology` / `Health Policy`         |
| Research Design       | `Observational Study`（当前证据等级 L1–L2）        |
| Funding               | 独立研究，无外部资助                                |
| Competing Interests   | `submissions/medrxiv/cover_letter_to_medrxiv.md`    |
| Data Availability     | `submissions/medrxiv/data_availability_statement.md`|
| Ethics Approval       | `submissions/medrxiv/ethics_and_consents.md`        |
| Author Contributions  | 见 `submission_manifest.json`                       |

## 关键合规要点（诚实版）

- **不是 RCT、不是前瞻性队列**——本研究为「框架 + 装置 + 验证装置」的
  方法学论文，证据等级为 L1（工程原型 + 合成装置验证）。medRxiv 对
  preprint 的证据要求宽于期刊，但摘要与结论段必须**如实标注**这一等级。
- **无人类临床数据**——不涉及 IRB 审批，但需声明「本研究未采集人类受试者
  数据」，伦理声明模板已给出。
- **案例库双 schema 事实**：29 条真证据 + 91 条合成夹具必须诚实说明，
  不得合并宣称「120 条真实案例」。
- **八轴是概念框架，不是诊断标准**——所有对外表述必须使用「wellness
  reference framework」而非「diagnostic framework」。

## 一键检查清单

上传前逐项勾选：

- [ ] 论文英文版全文（`HealthLens_论文_英文版_全文.md`）导出为 PDF
- [ ] Supplementary Data（`HealthLens_论文_计算验证_补充数据.csv`）打包为 zip
- [ ] Figure 1（`HealthLens_论文_框架概念图_Figure1.svg`）转为 300dpi PNG
- [ ] Zenodo DOI 已获取（`submissions/zenodo/`）
- [ ] 所有 DOI 引用可解析（`tools/verify_evidence_dois.py` 已跑）
- [ ] 计算验证结果可复现（`tools/engine_validation.py` 与 `validation_snapshots/BASELINE.json` 一致）
- [ ] 所有 8 轴参数外置（`config/axes/axes.yaml`）
- [ ] 中英论文轴数口径一致（8 轴，A–H；I/J reserved）
- [ ] 免责声明覆盖 wellness boundary 与 jurisdiction 差异

## 提交步骤（用户手动）

1. 登录 medRxiv → Create new submission
2. 按 `submission_manifest.json` 填标题、作者、机构、ORCID
3. 上传：
   - Manuscript: `HealthLens_论文_英文版_全文.md` 转 PDF
   - Supplementary Material: `HealthLens_论文_计算验证_补充数据.csv` + `data/doi_verification_results.json`
   - Figure: `HealthLens_论文_框架概念图_Figure1.svg`
   - Cover letter: `submissions/medrxiv/cover_letter_to_medrxiv.md`
4. 勾选所有声明（data availability / ethics / conflicts）
5. 上传后 medRxiv 会生成 preprint ID 与 DOI，返回 `https://www.medrxiv.org/content/XXXXXXXv1`
6. 提交后**保持版本可追溯**：每次修订通过 medRxiv 的 revision 流程，不改原 ID

## 未闭合（诚实）

- **需要真实用户账号**：AI 无法登录 medRxiv
- **需要机构邮箱**：如为独立研究，需至少 1 位 co-author 提供机构邮箱
- **需要用户判断是否投稿**：本包只提供材料，不代替用户的学术判断
