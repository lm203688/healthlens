# HealthLens MCP 上线操作步骤（需你亲自执行）

> 本文件配套 `mcp-server/server.json` v0.3.0 + 三个 GitHub Actions workflow。
> AI 已完成的部分：Dockerfile、语料镜像仓 `lm203688/tcm-mkg`、校验脚本、workflow 编排。
> **剩下全部需要你的账号凭证**，下面按依赖顺序拆成 6 个任务，每步都给链接和"看成功"判据。

---

## 总览

| # | 任务 | 耗时 | 需要什么凭证 | 依赖 |
|---|---|---:|---|---|
| 1 | Docker Hub 仓库 + 自动构建 | 15 min | Docker Hub 账号 | — |
| 2 | 语料镜像自动重发 | 5 min | GitHub PAT（public_repo） | — |
| 3 | PyPI 包发布 | 20 min | PyPI API token | — |
| 4 | Hugging Face 数据集 | 10 min | HF write token | — |
| 5 | MCP 官方 Registry | 10 min | 无（npx 登录） | **必须先完成 3** |
| 6 | 表单类市场（Glama / Smithery / mcp.so） | 30 min | 无 | 建议先做 3 |
| 7 | 工具重命名 `hl_*` → `healthlens_*` | 20 min | 你的产品决策 | 建议先做 5 |

**建议顺序：1 → 2 → 3 → 4 → 5 → 6**（1/2/3/4 互不依赖，可穿插；5 强依赖 3）。

统一 secrets 入口（1/2/3 都要用）：
👉 **https://github.com/lm203688/healthlens/settings/secrets/actions**
（New repository secret → Name 照抄 → Value 粘贴 → Add secret）

---

## 任务 1 — Docker Hub 镜像自动构建

目标：让 `lm203688/healthlens-mcp` 镜像能自动 build + push，目录站可以直接 `docker pull`。

### 1.1 建 Docker Hub 仓库

1. 打开 👉 **https://hub.docker.com/repositories/new**
2. Namespace：`lm203688`
3. Repository Name：`healthlens-mcp`（必须完全一致，workflow 里写死了）
4. 勾 **Public**
5. 点 **Create**

### 1.2 生成 Docker Hub Access Token

1. 打开 👉 **https://hub.docker.com/settings/security**
   （新版会自动跳到 https://app.docker.com/settings/profile/personal-access-tokens）
2. 点 **New Access Token**
3. Name 随便填 `healthlens-ci`，**权限勾 Read / Write / Delete**
4. 生成后页面只显示这一次 —— **马上复制存好**

### 1.3 加两个 GitHub secret

同一页面 👉 https://github.com/lm203688/healthlens/settings/secrets/actions

| Name | Value |
|---|---|
| `DOCKERHUB_USERNAME` | `lm203688` |
| `DOCKERHUB_TOKEN` | 上一步复制的 token |

### 1.4 触发构建

👉 **https://github.com/lm203688/healthlens/actions/workflows/docker-publish.yml** → 右侧 **Run workflow** → 点绿色按钮。

> 注意：缺任一 secret 时 job 会**静默 skip**（不红），所以必须先确认 secret 加对了。

**判成功**：约 5-10 分钟后打开 👉 **https://hub.docker.com/r/lm203688/healthlens-mcp/tags**
能看到 `latest` tag；本地再拉一次验证：

```powershell
docker pull lm203688/healthlens-mcp:latest
docker run --rm lm203688/healthlens-mcp:latest python -m healthlens_agent.mcp_server --demo
```

最后一行应打印出 6 个 L1/L2 工具（`hl_health_check`、`hl_search_knowledge`、`hl_get_axis_detail`、`hl_get_wellness_article`、`hl_suggest_general_diet`、`hl_suggest_general_motion`）。

---

## 任务 2 — 语料镜像自动重发

目标：`lm203688/tcm-mkg` 更新后一键重推（当前数据已在里面，这一步只是让以后能自动刷新）。

1. 打开 👉 **https://github.com/lm203688/healthlens/settings/secrets/actions** → New secret
   - Name：`GH_PAT`
   - Value：一个 classic PAT（个人设置 → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)），勾选 **public_repo**，expiration 选 `No expiration` 或 90 天
2. 打开 👉 **https://github.com/lm203688/healthlens/actions/workflows/publish-dataset.yml** → Run workflow

**判成功**：job 三步里最后一步 `Verify published blobs` 输出 `BAD: 0`。

> 想先看计划不写入：勾上 workflow 输入框里的 `dry_run`。

---

## 任务 3 — PyPI 包发布

目标：让 `pip install healthlens` 能装上 MCP server（**任务 5 的前置**）。

### 3.1 先确认包名没被占

打开 👉 **https://pypi.org/project/healthlens/** —— 显示 **404** 才说明可以发。如果被占了，改用 `healthlens-mcp`，并同步改 `mcp-server/server.json` 的 `packages[0].identifier`。

### 3.2 生成 PyPI token

1. 登录 👉 **https://pypi.org/manage/account/token/**
2. 填 name（如 `healthlens-ci`）→ 选择 scope **Entire account (all projects)**（只勾 healthlens 也行）→ Create token
3. 复制 `pypi-AgEIcHlwaS5vcmc...` 开头那串

### 3.3 加 secret

👉 https://github.com/lm203688/healthlens/settings/secrets/actions → New secret

| Name | Value |
|---|---|
| `PYPI_API_TOKEN` | 上一步的 `pypi-...` |

### 3.4 先 dry-run 验证（推荐）

👉 **https://github.com/lm203688/healthlens/actions/workflows/mcp-publish.yml**
→ Run workflow → 勾选 `Dry run only, do not upload` → 跑

看 `twine check` 有没有报错。**这步不上线，只验证包元数据合规**。

### 3.5 正式发布

同一个页面再触发一次，**不要勾 dry run**（或直接建 GitHub Release：https://github.com/lm203688/healthlens/releases/new，tag 填 `v0.3.0`，点 Publish —— release 事件会自己触发）。

**判成功**：job 最后一步 `Post-publish verify` 打印 `name: healthlens / version: 0.3.0`，
并且 👉 https://pypi.org/pypi/healthlens/json 能在浏览器返回 JSON。

---

## 任务 4 — Hugging Face 数据集

目标：一行 `load_dataset("lm203688/tcm-mkg")` 能读到 6207 实体语料。

### 4.1 生成 HF token

👉 **https://huggingface.co/settings/tokens** → New token (read) → type 选 **write** → 复制 `hf_...`

### 4.2 一条命令上传

在本项目根目录（`C:\Users\xing\Desktop\healthlens`）打开 **PowerShell**，依次粘贴：

```powershell
$env:HF_TOKEN = "hf_xxxxxxx你自己的token"
pip install huggingface_hub
python data\publish_hf.py
```

想顺便产出 parquet 分块：`python data\publish_hf.py --parquet`
想先试跑不上传：`python data\publish_hf.py --dry-run`

**不想装 Python 依赖**：打开 👉 **https://huggingface.co/new/dataset**
填 repo id `lm203688/tcm-mkg`，import 源选 "GitHub" 填 `https://github.com/lm203688/tcm-mkg` 即可，效果一样。

**判成功**：打开 👉 **https://huggingface.co/datasets/lm203688/tcm-mkg** 能看到卡片的 6.0 MB 文件列表。

---

## 任务 5 — MCP 官方 Registry

> ⚠️ **必须在任务 3 完成后做**。Registry 会真去解析 `packages[0]` 的 PyPI 包，没上线会被拒。

1. 打开 PowerShell（项目根目录）：
   ```powershell
   cd "C:\Users\xing\Desktop\healthlens\mcp-server"
   npx -y @modelcontextprotocol/publisher login github
   ```
   走 GitHub OAuth 授权（首次会弹浏览器）。

2. 发布：
   ```powershell
   copy server.json .\server.json
   npx -y @modelcontextprotocol/publisher publish
   ```
   （server.json 必须在当前目录，脚本才会读到它）

3. 若命令不存在，改用二进制方式（见 👉 https://github.com/modelcontextprotocol/registry 的 README，下载 `mcp-publisher` 后 `.\mcp-publisher.exe publish`）

**判成功**：访问 👉 **https://registry.modelcontextprotocol.io/servers/io.github.lm203688/healthlens** 能返回 JSON，
或者 👉 https://github.com/modelcontextprotocol/registry 上出现 pending/checking 状态的条目。

---

## 任务 6 — 表单类市场（低门槛、可批量）

| 市场 | 入口 | 填什么 |
|---|---|---|
| **Glama** | 👉 https://glama.ai/mcp （页面内点 **Submit a server**） | Name `HealthLens Wellness Knowledge`；Repo `https://github.com/lm203688/healthlens`；Install `pip install healthlens`；Category 选 Health / Wellness；Tags 带 `tcm`、`integrative-medicine` |
| **Smithery** | 👉 https://smithery.ai （Publish → 授权 GitHub → 选 `lm203688/healthlens`） | 自动读元数据，选 Docker 传输即可 |
| **mcp.so** | 👉 https://mcp.so （Submit 表单） | 同上 |
| **PulseMCP** | 👉 https://pulsemcp.com | 需 GitHub 仓库公开 |

> Glama 之前已通过，可看下你自己的条目作模板；Smithery 现在推荐直接用 Docker 传输（`lm203688/healthlens-mcp`），不用 pipe install。

---

## 任务 7 — 工具重命名 `hl_*` → `healthlens_*`（需你拍板）

**建议先做**：`hl_` 前缀不符合 MCP 命名惯例（多数 server 用前缀+动词，如 `gdrive_get_files`），
两个字母的 `hl_` 在 tool list 里辨识度低，且搜索时容易被 `healthlens` 关键词盖掉。

**但要一起改的地方**（改名要一次做完，否则线上/client 不一致）：
`mcp-server/server.json`、`mcp-server/README.md`、`mcp-server/Dockerfile`（无直接引用）、
`healthlens_agent/mcp_server.py` 里 `_TOOLS_L1/_TOOLS_L2/_TOOLS_L3` 的 key，
`app/api/mcp_http.py` 里 tools/call 的分发分支、以及前端 `frontend/` 若有引用。

**判成功**：`tools/list` 返回全换成新名字，且 `https://healthlens.cc/api/v1/mcp` 的 6 个工具调用仍正常。

---

## 卡住了怎么办

- **workflow 静默跳过** → 八成是 secret 没加或名字拼错，去 https://github.com/lm203688/healthlens/actions 看 job 是否出现
- **docker build 红** → README 里 `mcp-server/.dockerignore` 已排除大目录，红通常是 `pip install .` 拉超时，重跑一次即可
- **PyPI 说文件名已存在** → 版本号没涨，改 `pyproject.toml` 的 version 后再发
- **HF 说 repo 已存在** → 脚本幂等，直接重跑就行
- **Registry 说 package 解析失败** → 回任务 3，确认 https://pypi.org/project/healthlens/ 已能看到

每做完一步，回来让我复验 —— 我这边可以直接打 👉 https://healthlens.cc/api/v1/mcp 和各仓库 API 核对。
