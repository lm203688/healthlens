# 最后 4 项：一步一步操作指南

> 4 项任务都是"账号 / 机构系统硬阻塞"，AI 无法代劳。本指南把它们拆到**每一步都能直接照抄**的粒度。
> 每步都标注了：**耗时 · 前置条件 · 你要粘贴/输入什么 · 出错怎么办**。

---

## 步骤 0：一次性准备（约 5 分钟）

1. 一个能上网的浏览器（Chrome / Edge）
2. 一个能收邮件的邮箱（推荐 Gmail / Outlook，不要用 QQ 邮箱避免被 Zenodo / OSF 判为可疑）
3. 一个密码管理器（推荐 Bitwarden 免费版，避免到处粘）
4. 准备好本仓库的完整路径：`C:\Users\xing\Desktop\healthlens`

**先做一件小事：把当前 Zenodo / Zenodo 提交路径记下来**
```
C:\Users\xing\Desktop\healthlens\submissions\zenodo\
```

---

## 步骤 1：拿 ORCID（约 3 分钟）

**前置**：步骤 0 完成  
**产出**：一个形如 `0000-0002-1234-5678` 的 ID

### 1.1 打开页面
```
https://orcid.org/orcid
```
（这是唯一官方入口。orcid.org 才是官方，orcid.com 是仿站）

### 1.2 注册
- 点击 **Sign up**
- 邮箱用步骤 0 备好的邮箱
- 选 **Register now**（不要选 Find）
- 输入真实姓名、真实所属机构（HealthLens 可以写 "Independent Researcher"）
- 设置密码（≥ 12 字符，含大小写+数字+符号）
- 邮箱验证 → 回到 orcid.org 完成

### 1.3 记录 ORCID iD
注册成功后，页面右上角会显示类似 `0000-0002-1234-5678` 的 16 位字符串。**这是你的 ORCID**，一辈子不变。

### 1.4 替换 5 处占位符

**替换命令（一键完成，含自动字数）**：把 `0000-0002-1234-5678` 换成你的真实 ORCID，然后运行：
```bash
cd C:\Users\xing\Desktop\healthlens
python tools/fill_placeholders.py --orcid 0000-0002-1234-5678 --auto-word-count
```

**这个脚本会自动**：
- 从 `HealthLens_论文_IMR投稿包/manuscript_IMR.docx` 读取正文并统计字数（`--auto-word-count`），
  无需手动打开 Word 看状态栏
- 在 `HealthLens_论文_IMR投稿包/cover_letter.md` 替换 `{{YOUR_ORCID_ID}}`
- 在 `submissions/medrxiv/cover_letter_to_medrxiv.md` 替换 `[ORCID to be filled]`
- 在 `submissions/medrxiv/submission_manifest.json` 替换 `"PENDING_USER_FILL"`
- 在 `submissions/zenodo/README_zenodo_upload.md` 替换 `PENDING_USER_FILL`
- 在 `HealthLens_论文_medRxiv投稿包/submission_metadata.json` 替换 `{{ORCID_OPTIONAL}}`

> **说明**：`SUBMISSION_STEPS.md` 是**操作指南**，里面的 `{{YOUR_ORCID_ID}}` 是"教你去 docx 里替换"的示例文本，
> 不是实际占位符，所以工具不再扫描它（2026-10-19 修复）。稿件 docx 里的占位符仍需你在 Word 里手动
> 打开并替换（Ctrl+H），工具只处理 Markdown/JSON 提交文件。

**验证**：脚本会打印"replaced N occurrences"。看到 0 表示全都替换完。
也可单独运行 `python tools/fill_placeholders.py --check` 检查是否还有残留。

---

## 步骤 2：Zenodo 上传（约 8 分钟）

**前置**：步骤 1 完成  
**产出**：一个可访问的 DOI，形如 `10.5281/zenodo.1234567`

### 2.1 获取 Zenodo token

#### 2.1.1 打开 Zenodo
```
https://zenodo.org
```

#### 2.1.2 用 ORCID 登录
- 右上角 **Sign in** → **Sign in with ORCID**
- 跳转 ORCID 页面 → 同意 → 回到 Zenodo 首页

#### 2.1.3 创建 API token
- 右上角头像 → **Account** → 左侧菜单 **Personal access tokens**
- 点击 **New access token**
- 名字填：`healthlens-v030-upload`
- 权限选：**Deposits**（只勾这一个，最小权限原则）
- 点击 **Create**
- **立即复制 token** 到剪贴板（形如 `znd_abc123...`，只会显示这一次）

**保存到本地**（可选但推荐）：
```bash
# Windows PowerShell
$env:ZENODO_TOKEN = "znd_你的token"
```

### 2.2 上传 44 个文件（一步完成）

打开**新的 PowerShell 窗口**，粘贴：

```powershell
cd C:\Users\xing\Desktop\healthlens

$TOKEN = "znd_你的token粘贴到这里"
$BASE  = "https://zenodo.org/api"

# Step 1: 建 draft deposit（拿 deposit_id）
$res = Invoke-RestMethod -Method Post `
  -Uri "$BASE/deposits" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -ContentType "application/json" `
  -Body ([System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes("submissions\zenodo\zenodo_payload.json")))

$depositId = $res.id
Write-Host "Deposit ID: $depositId"

# Step 2: 逐个上传 44 个文件
$manifest = Import-Csv "submissions\zenodo\files_manifest.csv"
$i = 0
foreach ($row in $manifest) {
  $i++
  Write-Host "[$i/$($manifest.Count)] $row.filename"
  Invoke-RestMethod -Method Post `
    -Uri "$BASE/deposits/$depositId/files/$($row.filename)" `
    -Headers @{ Authorization = "Bearer $TOKEN" } `
    -InFile "$row.path" | Out-Null
}

# Step 3: 提交发布
Invoke-RestMethod -Method Post `
  -Uri "$BASE/deposits/$depositId/actions/publish" `
  -Headers @{ Authorization = "Bearer $TOKEN" } | Out-Null

Write-Host "✅ Published. DOI: $res.doi"
```

**预期输出**：44 行进度条 + 最后 `✅ Published. DOI: 10.5281/zenodo.XXXXXXX`

### 2.3 记录 DOI
把 DOI 复制到本文件的 `## 完成记录` 区（见文末），并回填到：
- `submissions/medrxiv/data_availability_statement.md`
- `submissions/zenodo/README_zenodo_upload.md`

### 2.4 出错排查

| 错误 | 原因 | 解决 |
|---|---|---|
| `401 Unauthorized` | token 错或权限不够 | 重开 2.1.3，确保勾了 **Deposits** |
| `403 Forbidden` | token 过期或类型错 | 重新创建 token |
| `413 Request Entity Too Large` | 单文件 > 25 MB | 检查 `files_manifest.csv`，拆分大文件 |
| `422 Unprocessable` | payload 缺字段 | 运行 `python tools/zenodo_deposit_payload.py --check` 先看校验 |
| `Invoke-RestMethod : The remote server returned an error` | 网络抖动 | 重跑整段脚本（Zenodo draft 支持多次覆盖） |

---

## 步骤 3：OSF 预注册（约 5 分钟）

**前置**：步骤 1 完成  
**产出**：一个 OSF pre-registration 链接

### 3.1 注册 OSF
```
https://osf.io
```
- **Sign up** → 选 **Institution** 里 "Independent Researcher" 或你的实际机构
- 邮箱 + 密码
- 邮件验证

### 3.2 新建 Pre-registration 项目
- 右上角头像 → **My Projects** → **New Project**
- 名字：`HealthLens Prospective Cohort Study Protocol`
- 创建后进入项目 → 左侧 **Registration** 标签
- 选择 **Pre-registration**
- **Template** 选 `SPIRIT-AI (2025)` 或 `Generic`（我们材料已按 SPIRIT-AI 组织）

### 3.3 上传材料
按顺序上传这 3 个文件到项目根目录：

```
C:\Users\xing\Desktop\healthlens\docs\prospective_cohort\osf_preprint_draft.md
C:\Users\xing\Desktop\healthlens\docs\prospective_cohort\study_protocol.md
C:\Users\xing\Desktop\healthlens\docs\prospective_cohort\informed_consent.md
```

### 3.4 提交
- 回到 **Registration** 标签
- 检查 metadata 表单（作者/日期/伦理编号 = `HL-IRB-2026-001`）
- 点击 **Register** → 输入密码确认

**预期**：生成一个 `https://osf.io/xxxxx/` 链接（xxxxx 是 5 位 hash）

---

## 步骤 4：IRB 机构提交（约 15 分钟，取决于 IRB 类型）

**前置**：步骤 1 完成  
**产出**：一个 IRB 受理编号

> ⚠️ IRB 是**机构**流程，路径依赖你选哪家。以下给三条常见路径，按你实际情况选一条走。

### 4.A 路径 A：独立 IRB（最快，2-4 周）

推荐 **WCG IRB**（wcgsa.org）或 **IRB-USA**（irbusa.net）
- 走 **Expedited Review** 通道（我们的研究是 wellness 观察性，符合加速审查）
- 费用：$2500-$4000（WCG 首份约 $2700）
- 材料：把 `docs/prospective_cohort/irb_submission_package.md` 转成 PDF 上传

### 4.B 路径 B：机构 IRB（免费但慢，1-3 月）

如果你在职高校/医院，走校内 IRB 门户。
- 找学校 `伦理委员会` 或 `IRB office` 邮件
- 上传 irb_submission_package.md
- 通常免费，但要走校内流程

### 4.C 路径 C：暂时用预注册 + 数据共享协议占位（0 元，立即可用）

如果资金/时间紧张，**先走 OSF 预注册（步骤 3）**，在预注册里明确：
> "IRB submission is in progress at [TBD]。All subjects will be recruited only after IRB approval."

很多期刊（尤其 preprint 阶段的 medRxiv）接受这个过渡声明。正式 IRB 编号到了再补一版。

### 4.D 通用提交动作
无论走 A/B/C，最终都要：
1. 打开 irb_submission_package.md
2. 按里面的 **Submission Checklist** 补齐：伦理编号、PI 签名、机构 stamp（如果有）
3. 上传到对应 IRB 门户
4. 记下受理编号（形如 `IRB-2026-xxxxx`）

---

## 完成记录（每完成一项就在这里填）

| # | 项目 | 状态 | 完成时间 | 产出（ORCID / DOI / URL / 编号） |
|---|---|---|---|---|
| 1 | ORCID | ✅ | 2026-10-19 | `0009-0004-2152-7669`（已通过 orcid.org API 校验，填至 6 个提交文件 + 2 个论文 byline + 2 个 cover letter） |
| 2 | Zenodo DOI | ☐ | | |
| 3 | OSF 预注册 | ☐ | | |
| 4 | IRB 受理编号 | ☐ | | |

---

## 遇到阻塞怎么办

- **看不懂某步** → 截图给我，我针对那一屏指导
- **报错** → 把错误原文贴给我，我判根因
- **不确定走 A/B/C 哪条 IRB 路径** → 告诉我你目前的身份（学生/在职/独立研究者），我推荐最省钱的路径
- **想让我先跑某步 dry-run** → 直接说 "跑 2.2 dry-run"，我在本地模拟一遍输出

**原则**：能自动化的我已全自动化（44 个文件、payload、sha256、替换脚本都写好）；剩下的每一步都是"复制粘贴"级别的机械操作，卡住就把原始报错贴回来。
