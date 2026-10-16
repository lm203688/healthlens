# GraphRAG 公开前检查清单

**版本**：v0.1.0-draft · 2026-10-16
**规范**：对齐报告 §9 风险清单「公开图谱/基准引入抽取攻击与滥用」
**关联代码**：`tools/redact_for_public_release.py`（已交付）+ L4 团队 `graphrag_security.py`（待交付）
**关联文档**：`docs/zenodo_publication/README.md` §5、`COMMUNITY_USE_POLICY.md` §6

> 参考：`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6、§9。
> 本清单是 Zenodo 上传前的**必需前置**——任何一项未勾选都须暂停发布。

---

## 检查清单（24 项）

### A. 脱敏与数据最小化（6 项）

- [ ] **A1**：所有字段经 `tools/redact_for_public_release.py` 处理，输出前 diff 审计
- [ ] **A2**：`graphrag/` 目录下的敏感子集（内部标注、内部推理轨迹）已剔除或明确脱敏
- [ ] **A3**：`--strip-bibliographic` 类脱敏能力已测试，可开关
- [ ] **A4**：`classical_slices.json` 中每条 `needs_expert_review=true` 字段保留，禁止移除
- [ ] **A5**：无参与者个人身份信息（PII）泄露，通过 `grep` 关键词扫描：`id_card|email|phone|mobile|地址|护照`
- [ ] **A6**：无内部 API token / 私钥 / 密码泄露，通过 `.gitignore` + secret scan 检查

### B. 许可与署名（3 项）

- [ ] **B1**：每个文件头部含 CC-BY 4.0 许可链接
- [ ] **B2**：`CITATION.cff` 中 `authors`、`doi`、`year` 与 Zenodo 上传时一致
- [ ] **B3**：`COMMUNITY_USE_POLICY.md` 与本清单同步版本

### C. 引用格式（3 项）

- [ ] **C1**：BibTeX 示例已验证（可用 BibTeX 解析器 `bibtex2html` 或 `pandoc`）
- [ ] **C2**：Zotero 自动引用配置：Zenodo 上传后测试一次 Zotero 自动抓取
- [ ] **C3**：中文引用示例已验证（GB/T 7714-2015 格式）

### D. 抽取攻击评估（5 项）

- [ ] **D1**：`graphrag_security.py` 抽取攻击评估完成（L4 团队交付）
- [ ] **D2**：Prompt-injection 测试：`taxonomy traversal`、`embedding leakage`、`system-prompt leak` 三项攻击均无泄露
- [ ] **D3**：Adversarial probing：随机 seed 100 次，无敏感字段被反推
- [ ] **D4**：与内部知识图谱 diff，确认无内部-only 字段被意外纳入
- [ ] **D5**：抽取攻击评估报告已附上 Zenodo deposit（作为 supporting file）

### E. 变更日志与版本（3 项）

- [ ] **E1**：本清单随每次发布打 tag（`graphrag_release_vX.Y.Z`）
- [ ] **E2**：变更日志在 `docs/zenodo_publication/CHANGELOG.md`（本次发布前补齐，若尚未创建则本次作为 v0.1.0-draft 初稿）
- [ ] **E3**：所有子集有独立版本号，与 `dataset_manifest.json` 中的 `manifest_version` 一致

### F. 完整性与可复现（4 项）

- [ ] **F1**：每个文件含 SHA-256 校验和（`stat -c%s` + `sha256sum`）
- [ ] **F2**：`validation_snapshots/BASELINE.json` 已附；复现脚本可执行
- [ ] **F3**：`data/case_evidence_db.json` 中的 `citation_status` 分布已核对（verified/verified_crossref/traditional/synthetic_validation/unverified_no_publication）
- [ ] **F4**：`data/case_evidence_db_report_2026-10-16.md` 覆盖率报告已附；诚实披露 11.7% 而非 95%

### G. 元数据与合规（3 项）

- [ ] **G1**：`dataset_manifest.json` 中 `creators[].orcid` 已由研究者填入（非空）
- [ ] **G2**：`upload_notes` 中 API endpoint、auth、steps、prerequisites 五项已核对
- [ ] **G3**：合规评估：PIPL + GDPR Art.9 双法域评估完成

---

## 使用指南

1. **发布前**：逐项勾选，任何未勾选的项须记录在 `docs/zenodo_publication/CHANGELOG.md` 中作为 known issues；
2. **发布时**：将本清单的勾选版本随 Zenodo deposit 一起上传；
3. **发布后**：任何用户报告抽取攻击成功或数据泄露，触发 §D 重新评估。

## 与 L4 团队 `graphrag_security.py` 的分工

- **本清单**：定义"发布前必须完成的检查项"（人工/流程层面）；
- **`graphrag_security.py`**：实现 D1-D4 项的自动化检查（代码层面）；
- **`tools/redact_for_public_release.py`**：实现 A1-A5 项的自动化脱敏（已交付）；
- 三者构成"人工清单 + 自动化工具 + 代码实现"的三层防线。

## 版本历史

- v0.1.0-draft（2026-10-16）：初稿，等待 L4 团队 `graphrag_security.py` 交付后复核 D 部分

---

**wellness 声明**：本清单服务于 wellness 研究数据集的公开发布；不覆盖医疗数据集的伦理审查要求。
