# IMR 投稿逐步指南

**目标期刊**：Integrative Medicine Research (IMR)
**投稿系统**：Editorial Manager — https://www.editorialmanager.com/IMRES/
**审稿周期**：中位 12 周（约 2–3 个月）
**作者费用**：$0（KIOM 全额承担 APC）

---

## 阶段 0：投稿前准备（1–2 天）

### 0.1 生成 ORCID iD（必须）

IMR **强制要求所有作者 ORCID iD**。

1. 打开 https://orcid.org
2. 点击 "Sign in / Create account" → "Create account"
3. 用真实姓名 + 邮箱注册（用你通讯作者邮箱 `corresponding@healthlens.cc`）
4. 注册完成会得到 16 位 ORCID，格式 `0000-0002-XXXX-XXXX`
5. 在 ORCID 页面填上：
   - 英文名：Li Xing
   - 单位：HealthLens, Hangzhou, China
   - 邮箱：corresponding@healthlens.cc
   - 研究领域标签：Integrative Medicine, Systems Biology, Aging, TCM

### 0.2 填充稿件占位符

打开 `manuscript_IMR.docx`，全文搜索并替换：

| 占位符 | 替换为 |
|---|---|
| `{{YOUR_ORCID_ID}}` | 你刚拿到的 ORCID（如 `0000-0002-1234-5678`） |
| `{{YOUR_PHONE}}` | 你的手机或邮箱接收电话（+86 前缀） |
| `{{WORD_COUNT}}` | Word 状态栏字数（打开稿件底部左角） |

同样处理 `cover_letter.md` 里的占位符。

### 0.3 稿件字数检查

- Word 底部状态栏显示 word count
- IMR 无硬字数上限，但一般 Original Article 6000–8000 词
- 本稿件约 4000–5000 词（含 abstract 250 词 + references）——属于**偏短但可接受**的范围

### 0.4 参考文献核实

**关键步骤**：本稿件参考文献由 AI 辅助生成后由作者人工核实。投稿前必须逐条打开 DOI 验证：

```
[1]  https://doi.org/10.1016/j.clnesp.2024.11.002
[3]  https://doi.org/10.1038/s41467-024-45260-9
[5]  https://doi.org/10.1016/j.ebiom.2019.08.069
[6]  https://doi.org/10.1038/nrg2850
[8]  https://doi.org/10.1038/s41591-024-03375-y
[9]  https://doi.org/10.1016/j.jhep.2025.06.005
[15] https://doi.org/10.1152/japplphysiol.00999.2009
[18] https://doi.org/10.1038/s41591-026-04102-8
```

用 Web of Science 或 PubMed 交叉核对作者列表和页码。**特别是 [18] AFFIRM 是 2026 年预印本**，投稿前必须确认真实出版状态。

### 0.5 伦理 + 数据声明

- 无人类参与者 → 稿件已写 "No IRB approval required"
- 数据公开在 GitHub → 已写 Data Availability

### 0.6 语言润色（强烈建议）

IMR 明确要求非母语作者"须经英语母语人士或专业英语编辑服务检查"。

**推荐免费方案**：
1. Grammarly Free 版（https://grammarly.com）—— 免费额度足够
2. 或者用 DeepL Write（https://www.deepl.com/translate）—— 有每日免费额度

**付费方案**（如需正式润色证书）：
- Enago Editage（IMR 合作）—— 约 $200
- AJE（American Journal Experts）—— 约 $300

如果预算紧张，就用 Grammarly Free + 自查即可，IMR 不强制要润色证明。

---

## 阶段 1：预印本抢优先权（可选但强烈推荐）

**IMR 明确接受预印本**。抢优先权可以保护你的创新，且不影响期刊投稿。

1. 打开 https://www.medrxiv.org
2. 点击 "Sign in" → "Register" 用真实信息注册
3. 选择 "New preprint submission"
4. 上传：
   - Manuscript (PDF 或 DOCX)
   - Supplementary Materials（如 case_evidence_db.json）
5. 填写元数据：标题、作者、摘要、关键词、作者贡献、ORCID
6. 提交后 **48 小时内**会分配 DOI，可用作引用

**优势**：
- 48 小时出 DOI
- 不影响 IMR 投稿（IMR 明确允许）
- 可以引用自己的预印本
- 保护知识产权

---

## 阶段 2：注册 Editorial Manager（15 分钟）

### 2.1 创建账户

1. 打开 https://www.editorialmanager.com/IMRES/
2. 右侧点击 "New here? Create an Account"
3. 填写：
   - First name / Last name：真实姓名
   - Email：通讯作者邮箱（`corresponding@healthlens.cc`）
   - Password：8 位以上强密码
   - User type：**Author**
   - Institution：HealthLens
   - Country：China
4. 点击 "Create Account"
5. 打开邮箱点击激活链接

### 2.2 完善个人资料

登录 EM 后：

1. 右上角点击你的名字 → "Author Profile"
2. 填写：
   - **ORCID iD**（IMR 强制！）
   - Affiliation（HealthLens, Hangzhou, China）
   - Postal Address
   - Phone number
3. 点击 "Save"

---

## 阶段 3：稿件提交流程（30–45 分钟）

### 3.1 进入投稿界面

1. 登录后，顶部菜单 "Submit Manuscript" → "Submit a Manuscript"
2. 阅读免责声明 → 勾选 "I agree" → "Next"

### 3.2 Step 1: Manuscript Information

**Manuscript Type**：选择 **Original Article**

**Title**：完整复制稿件标题
```
An Integrated Steady-State Biology Framework for Non-Pharmacological Longevity Intervention: From Classical-Text and Genome Fusion to Closed-Loop Validation
```

**Abstract**：粘贴 Abstract 四段结构化摘要（250 词以内）

**Keywords**（3–5 个）：
```
integrative medicine; homeostasis; autophagy; mitochondria; circadian rhythm
```

**Author Order**：只填你一人即可（如多作者按顺序填）

**Contributing Authors**：填 ORCID + 完整信息

**Corresponding Author**：填你的完整通讯信息

### 3.3 Step 2: Manuscript Data

**Confidential Notes to the Editor**（不公开）：
```
This is the first framework paper proposing the ISSBF. The manuscript is original and has not been submitted elsewhere. The case library is publicly available. All computational validation code is open-source. The framework is a non-medical decision-support paradigm, not a clinical protocol.
```

**Cover Letter**（公开）：粘贴 `cover_letter.md` 内容

### 3.4 Step 3: Manuscript Checklist

IMR 会问一系列问题，标准答案：

- Is the submission original? **Yes**
- Is it not under consideration elsewhere? **Yes**
- Do all authors approve the manuscript? **Yes**
- Are all conflicts of interest disclosed? **Yes** (none)
- Is the ethical approval statement included? **Yes** (no human participants)
- Are data available? **Yes** (GitHub repository)

### 3.5 Step 4: Upload Files

**必须上传的文件**：

| 文件 | 格式 | 说明 |
|---|---|---|
| `manuscript_IMR.docx` | DOCX | 主稿件（**必传**） |
| `CoverLetter.docx` | DOCX | 投稿信（如系统要求文件） |
| `Figure1_Ten_Axis_Framework.eps` | EPS | Figure 1 矢量图（**推荐**） |
| `Figure1_Ten_Axis_Framework.png` | PNG | Figure 1 备份（600 dpi） |

**不需要单独上传**（已在稿件内）：
- Table 1（IMR 要求放在文末）
- References（IMR 要求 Vancouver 格式）
- 所有声明（Ethics/Funding/COI/Data/AI/CRediT）

### 3.6 Step 5: Review and Submit

1. 检查所有字段无误
2. 勾选同意所有条款
3. 点击 **"Submit Manuscript"**
4. 保存确认邮件（含稿件编号，如 `IMR-D-26-00000`）

---

## 阶段 4：审稿后跟进

### 4.1 时间预期

| 阶段 | 预期时间 |
|---|---|
| 编辑初审决定送审/直接拒 | 2 周内 |
| 同行评审（2 位审稿人） | 4–10 周 |
| 决定通知 | 通常 12 周内 |

### 4.2 常见决策

- **Accept**（约 15–20%）→ 直接进入校样阶段
- **Minor Revision**（约 20–30%）→ 2–3 周修改后接受概率高
- **Major Revision**（约 15–20%）→ 需要 1–2 个月认真修改
- **Reject with invitation to resubmit**（约 15%）→ 按建议修改后可重投
- **Reject**（约 30–40%）→ 转投其他期刊

### 4.3 修改稿回复信

无论 minor 还是 major revision，都要写 **Response Letter**：

```markdown
Dear Editor and Reviewers,

Thank you for your careful review. We have addressed all concerns point-by-point
below. Changes to the manuscript are highlighted in yellow.

---

**Reviewer 1, Comment 1**: [quote reviewer comment]
**Response**: [your response]
**Change**: [quote modified text from manuscript, with page/line reference]

---

**Reviewer 2, Comment 1**: ...
```

**技巧**：
- 逐条回复，不要遗漏任何评论
- 即使不同意也要礼貌说明理由
- 修改处黄色高亮（EM 提供格式工具）

---

## 阶段 5：接受后（如果接受了）

### 5.1 校样（Proof）

- 2 周内会收到校样邮件
- **必须在 48 小时内回复修改意见**
- 主要检查：拼写、作者信息、参考文献、图表编号
- 版权转让函由通讯作者签署（邮件形式）

### 5.2 出版

- IMR 是 **Article-Based Publishing**（单篇立即在线发布）
- 接受即得 DOI，可立即引用
- 版权：**CC BY-NC-ND 4.0**（署名+非商业+禁止演绎）
- 永久存储在 ScienceDirect 平台

### 5.3 作者自存档（Green OA）

- 作者可在 6 个月后自存档在个人主页/机构库
- 建议同步上传到 arXiv（q-bio）或 CORE 数据库

---

## 常见坑位

### ❌ 一稿双投

**违反 ICMJE 规则**。IMR 期间不能同时投给 JIM 或 JTCM。

### ❌ 未替换占位符

提交前必须搜索 `{{YOUR_` 确认所有占位符已替换。

### ❌ 摘要超 250 词

用 Word 只选中摘要段落（不含关键词）看字数。

### ❌ 图表嵌入稿件文件

IMR 明确要求"图片作为单独文件上传"，不要在稿件里嵌入图片。

### ❌ 缺少 ORCID

IMR 强制要求，提交时如未填会被退回。

### ❌ AI 生成参考文献未核实

AI 工具可能生成不存在的文献（"幻觉"）。IMR 明确要求作者对 AI 使用负责。**必须逐条打开 DOI 确认**。

---

## 决策清单（提交前最后确认）

- [ ] ORCID 已注册并填到稿件和 EM 账户
- [ ] 稿件占位符全部替换（`{{YOUR_ORCID_ID}}` `{{YOUR_PHONE}}` `{{WORD_COUNT}}`）
- [ ] Cover Letter 占位符已替换
- [ ] 摘要 250 词以内
- [ ] 章节顺序：Introduction → Methods → Results → Discussion
- [ ] 参考文献格式为 Vancouver 风格（数字上标 + MEDLINE 期刊缩写）
- [ ] 所有 24 篇参考文献 DOI 已人工核实
- [ ] Table 1 在文末
- [ ] Figure 1 图例在参考文献之后
- [ ] Figure 文件 EPS + PNG 单独准备好
- [ ] CRediT 作者贡献格式（本稿件单人 CRediT，已按 14 类填完）
- [ ] Ethics Statement / Funding / COI / Data Availability 都已写
- [ ] IMR AI 声明章节已写（"Declaration of generative AI..."）
- [ ] 投稿信已填日期
- [ ] 无人类参与者已在 Ethics 声明中说明
- [ ] EM 账户已注册、作者信息已完善、ORCID 已关联
- [ ] 未在任何其他期刊挂稿（含 medRxiv 是否已投，如已投需在 Cover Letter 中提及）

---

## 备份与后续

- 提交通道：**Editorial Manager**（https://www.editorialmanager.com/IMRES/）
- 期刊官网：**https://www.imr-journal.com**
- 编辑邮箱：**imr@kiom.re.kr**（仅编辑事务）
- 技术支持：**https://service.elsevier.com/app/home/supporthub/publishing/**

如审稿被拒，转投次序建议：
1. **Journal of Integrative Medicine (JIM)** — IF 5.2，注意彩图选 online only 避免印刷费
2. **Journal of Traditional Chinese Medicine (JTCM)** — IF 2.2，60 天快审
3. **Chinese Journal of Integrative Medicine (CJIM)** — IF 2.5，主题最贴

---

## 一句话总结

**先填 ORCID + 替换占位符 + 人工核实参考文献 DOI → 注册 EM 账户 → 按 Step 1–5 上传稿件+图+投稿信 → 30 分钟内提交完成。剩余就是等 12 周审稿决定。**
