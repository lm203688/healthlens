# HealthLens MCP 上线 — 实际状态与剩余步骤

> 更新：2026-10-03。本文件取代 2026-10-02 版的手册。
> 现在**大部分是 AI 已闭环的**，你真正要点的按钮只剩 2 个（都只要 1 次、约 3 分钟）。

---

## 一、当前状态（AI 实测）

| 项 | 状态 | 证据 |
|---|---|---|
| MCP HTTP 端点 | ✅ 线上可用 | `POST https://healthlens.cc/api/v1/mcp` → `initialize` 返回 `healthlens-mcp v0.3.0`，`tools/list` 返回 6 个 L1/L2 工具 |
| MCP stdio 镜像 | ✅ 已构建并推 GHCR | `ghcr.io/lm203688/healthlens-mcp:latest`；workflow run `docker-publish` 绿 |
| 语料镜像仓 | ✅ 已更新 | `lm203688/tcm-mkg` 新 commit `c08654d4`（6.0 MB 语料全部字节一致） |
| 数据集发布自动化 | ✅ 零 secret | `publish_dataset_repo.py` 无 token 也能推（目标仓公开），CI 不再因缺 `gh_pat.txt` 崩 |
| PyPI 包 | 🟡 **干跑通过，待你发一步** | `mcp-publish.yml` dry-run 已绿（`python -m build` + `twine check` 全过）；只差仓库 secret `PYPI_API_TOKEN` |
| Hugging Face 数据集 | 🟡 可选（有零凭证路径） | GitHub 网页导入即可，不用 token |
| 官方 MCP Registry | 🔒 卡在 PyPI | 必须先完成任务 3；且 `registry.modelcontextprotocol.io` 从国内访问不稳定 |
| Docker Hub | ⛔ 放弃 | 大陆 TLS 不可达，不再作为分发源 |

已上线的 6 个工具（`tools/list` 实测）：
`hl_health_check`、`hl_search_knowledge`、`hl_get_axis_detail`、`hl_get_wellness_article`、`hl_suggest_general_diet`、`hl_suggest_general_motion`

---

## 二、你只需要做的两件事

### 任务 A — 给 PyPI 发一个 token（3 分钟，1 次）

发布 `pip install healthlens` 的入口，也是官方 Registry 的前置。

1. 👉 https://pypi.org/manage/account/token/ → name 填 `healthlens-ci` → scope 选 **Entire account** → **Create token**
2. 👉 https://github.com/lm203688/healthlens/settings/secrets/actions → **New repository secret**
   - Name：`PYPI_API_TOKEN`
   - Value：粘上面那串 `pypi-...`
3. 👉 https://github.com/lm203688/healthlens/actions/workflows/mcp-publish.yml → **Run workflow** → **不要勾** `Dry run only` → 跑
4. 判成功：最后一步 `Post-publish verify` 打印 `name: healthlens / version: 0.3.0`，
   并且 👉 https://pypi.org/pypi/healthlens/json 能在浏览器返回 JSON

> 包名 `healthlens` 与 `healthlens-mcp` 我查过，**PyPI 上都没被占用**，直接发就能占住。
> 想先在网页上确认：https://pypi.org/project/healthlens/ 应显示 404。

### 任务 B — HF 数据集（可选，两条路二选一）

- **零凭证**：打开 👉 https://huggingface.co/new/dataset → repo id 填 `lm203688/tcm-mkg` → import 源选 GitHub → 填 `https://github.com/lm203688/tcm-mkg`
- **想用脚本**：👉 https://huggingface.co/settings/tokens 建 write token → 项目根目录 PowerShell：
  ```powershell
  $env:HF_TOKEN = "hf_xxxx"
  python data\publish_hf.py
  ```

判成功：👉 https://huggingface.co/datasets/lm203688/tcm-mkg 能看到 6.0 MB 文件列表。

---

## 三、AI 已闭环、你不用管的部分

| 环节 | 说明 |
|---|---|
| 镜像构建与 smoke test | `docker-publish.yml` 用自带 `GITHUB_TOKEN`（`packages: write`），**零 secret**。smoke test 跑 `python -m healthlens_agent.mcp_server --demo`，打不进镜像就判红 |
| 语料重发 | `publish-dataset.yml` 推 `lm203688/tcm-mkg`；脚本无 token 时自动降级匿名（公开仓），CI 不再崩 |
| 单测 | `Agent Library Test` 48/48 过；`Skills Test` 3/3 过；`docker-publish` smoke 过 |
| 客户端接入配置 | 见下节，复制即用 |

### 客户端配置（复制即用）

```json
{
  "mcpServers": {
    "healthlens": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/lm203688/healthlens-mcp:latest"]
    }
  }
}
```

国内验证：`ghcr.io` 实测可达（返回 401 而非超时），比 Docker Hub 稳。
若报 `unauthorized: authentication required`，先 `docker login ghcr.io` 一次。

不走容器也行，直接用线上端点（L1/L2 无需鉴权）：

```bash
curl -X POST https://healthlens.cc/api/v1/mcp \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
```

> ⚠️ 不带 `User-Agent` 会被 Cloudflare 1010 拦成 403，这是 CF 的机器人保护，不是服务挂了。

---

## 四、做完后剩下的两个决策（不急）

### 4.1 官方 MCP Registry（依赖任务 A）

1. 项目根目录 PowerShell：
   ```powershell
   cd "C:\Users\xing\Desktop\healthlens\mcp-server"
   npx -y @modelcontextprotocol/publisher login github
   npx -y @modelcontextprotocol/publisher publish
   ```
2. 判成功：👉 https://registry.modelcontextprotocol.io/servers/io.github.lm203688/healthlens 返回 JSON

> 注意：**`smithery-ai/registry` 这个仓库不存在**（实测 404）。官方社区 registry 是
> https://github.com/modelcontextprotocol/registry ，发布走上面的 `mcp-publisher` CLI，
> 支持 GitHub OAuth / OIDC。该站国内访问不稳定，别急，任务 A 做完再试也不迟。
> `server.json` 里的 `packages[0]` 是 `pypi: healthlens`，Registry 会真去解析它并校验
> README 里的 `mcp-name:` 行 —— 所以任务 A 必须先完成。

### 4.2 工具命名 `hl_*` → `healthlens_*`（产品决策）

`hl_` 两字母前缀在工具列表里辨识度低。要改必须一次性全改：
`mcp-server/server.json`、`healthlens_agent/mcp_server.py`（`_TOOLS_L1/L2/L3` 的 key）、
`app/api/mcp_http.py` 的分发分支、前端若有引用、`mcp-server/README.md`。

判成功：`tools/list` 全换名，且线上 6 个工具调用仍正常。
**建议：等 Registry 收录后再改，避免改完又得重跑一次收录。**

---

## 五、踩坑速查

| 现象 | 原因 / 处理 |
|---|---|
| `docker-publish` 红，日志 `FileNotFoundError: 未找到融合引擎：/app/app/lib/fusion_engine.py` | MCP 瘦镜像不带 `app/` 目录，`healthlens_agent/__init__.py` 却在 import 期经 `flow.py` 触发加载。已修：`_loader.load_fusion_engine()` 缺失时返回 `None` 而不是抛异常，镜像里也 COPY 了 `app/lib/fusion_engine.py` |
| `publish-dataset` 红，`FileNotFoundError: .../gh_pat.txt` | 脚本硬读本地 token 文件，CI 上没有。已修：无 token 时降级匿名（目标仓公开） |
| CI `Lint & Test` 红 | `tests/conftest.py` 报 `No module named 'app.models.points'` —— 那两个模型文件**从来没推到 GitHub**（历史单文件推送漏项），远端 checkout 里根本没有。已补齐 44 个漏推文件；同时 ratchet 逻辑改成「收集期崩溃」与「真有失败」分开报 |
| CI `Agent Library Test` 红 | `ruff check healthlens_agent` 有 10 处 UP017/W292。已自动修完，本地复检 `All checks passed!` |
| 本地想复现「无 FastAPI」的 CI 环境 | `PYTHONPATH=<repo>/.workbuddy/cache/blocker` 后再跑 pytest，可阻断 web 栈导入（48 passed） |

---

## 六、给 AI 的复验入口

- 线上端点：`POST https://healthlens.cc/api/v1/mcp`
- 镜像：`ghcr.io/lm203688/healthlens-mcp:latest`
- 语料：`https://github.com/lm203688/tcm-mkg`
- 工作流：`https://github.com/lm203688/healthlens/actions`
