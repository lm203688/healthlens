# HealthLens MCP 上架指南

**目标**：把 HealthLens MCP Server 上架到主流 MCP marketplace，被 Claude / Cursor / Cline / Windsurf / Coze 等 Agent 消费。

**前置**：完成 `docs/healthlens-mcp-design.md` 中定义的分层策略。默认仅暴露 L1+L2 工具（安全，无个人数据）。

---

## 一、市场全景（2026-09 数据）

| 指标 | 数值 | 来源 |
|---|---|---|
| 官方 MCP Registry | 9,652 servers | MCP Registry API |
| Glama 索引 | 19,800+ servers / 229,800+ tools | Glama |
| Skillful.sh 全域 | 587,816 tools | skillful.sh |
| 平均 trust score | 65.5/100（70+ 高分仅 12.9%） | Nerq Q1 2026 |
| 已被放弃比例 | 52% | Bex / Cloudflare 审计 |
| 生产级比例 | 17% | Bex / Cloudflare 审计 |

**含义**：MCP 生态增长极快、质量极散，"可信 wellness 数据源" 是差异化位置。

---

## 二、上架市场清单（按 ROI 排序）

### 第一梯队：立即上架（1-3 天，免费）

| # | 市场 | URL | 提交方式 | 优先级 |
|---|---|---|---|:---:|
| 1 | **Glama** | https://glama.ai/mcp | Web 表单 | P0 |
| 2 | **Official MCP Registry** | https://github.com/modelcontextprotocol/servers | GitHub PR | P0 |
| 3 | **Smithery** | https://smithery.ai | GitHub 仓库配置 | P0 |
| 4 | **mcp.so** | https://mcp.so | Web 表单 | P1 |
| 5 | **PulseMCP** | https://pulsemcp.com | Web 表单 | P1 |

### 第二梯队：需审核（1-2 周）

| # | 市场 | 备注 |
|---|---|---|
| 6 | **Coze 插件市场** | 需企业账户 + 审核 |
| 7 | **Dify 插件市场** | 需企业账户 |
| 8 | **LobeChat 插件** | GitHub PR |
| 9 | **Cline MCP 集成** | 官方列表 PR |

### 第三梯队：布局（未来）

| # | 市场 | 备注 |
|---|---|---|
| 10 | **Muse (Meta)** | 无第三方 MCP 接入接口，暂不可上架 |
| 11 | **Grok Bot (xAI)** | 无第三方 MCP 接入接口，暂不可上架 |
| 12 | **ChatGPT Custom GPTs** | 需 OpenAI 官方接入 |
| 13 | **Gemini Apps** | 需 Google 官方接入 |

---

## 三、上架前置准备

### 1. GitHub 仓库公开化

HealthLens 仓库目前 `lm203688/healthlens` 需设为 public（如果当前是 private）：

```bash
# 检查当前可见性
curl -s -H "Authorization: token $GH_TOKEN" \
  https://api.github.com/repos/lm203688/healthlens | jq '.private'
```

### 2. 推送 MCP server 到 main

```bash
git add healthlens_agent/mcp_server.py healthlens_agent/__main__.py \
        docs/healthlens-mcp-design.md docs/mcp-marketplace-submission.md \
        mcp-server/
git commit -m "feat(mcp): add tiered MCP server v0.2 + marketplace metadata"
git push origin main
```

### 3. 发布 PyPI 包（可选但推荐）

```bash
cd /path/to/healthlens
pip install build twine
python -m build
python -m twine upload dist/*
```

包名 `healthlens` 需在 PyPI 上未注册。如冲突，改为 `healthlens-mcp-server`（需修改 pyproject.toml 的 `name` 字段）。

### 4. 验证安装可用

```bash
pip install healthlens-mcp-server  # 或 pip install healthlens
python -m healthlens_agent mcp --demo
```

---

## 四、各市场具体提交步骤

### 1. Glama（P0，最简单）

**URL**：https://glama.ai/mcp

**步骤**：
1. 访问 https://glama.ai/mcp
2. 点 "Submit a Server" 或 "Add your server"
3. 填写表单：
   - **Name**：`HealthLens Wellness Knowledge`
   - **Repository URL**：`https://github.com/lm203688/healthlens`
   - **Description**：从 `mcp-server/server.json` 的 description 字段复制
   - **Install Command**：`pip install healthlens-mcp-server`
   - **Categories**：Health, Wellness, Integrative Medicine
   - **Tags**：wellness, health, tcm, integrative-medicine, personalized-medicine
4. 提交，等待审核（通常 < 24h）

**参考**：aishield 已上架 Glama，可看其信息作为模板。

### 2. Official MCP Registry（P0，最权威）

**URL**：https://github.com/modelcontextprotocol/servers

**步骤**：
1. Fork `modelcontextprotocol/servers` 仓库
2. 在 `src/` 目录下找到类似分类文件夹（如 `src/health/`），如果没有则创建
3. 添加新条目：

```markdown
### HealthLens Wellness Knowledge

- **Repository**: https://github.com/lm203688/healthlens
- **Website**: https://healthlens.cc
- **Description**: MCP server exposing HealthLens wellness knowledge: 8-axis integrative framework, TCM knowledge base search, general diet & motion guidance. Safe by default.
- **Install**: `pip install healthlens-mcp-server`
- **License**: MIT
```

4. 提交 PR，标题如：`Add HealthLens wellness MCP server`
5. 等待审核合并（可能 3-7 天）

**参考**：aishield 已提交过官方 PR，可参考 `docs/awesome-mcp-servers-pr.md`。

### 3. Smithery（P0，GitHub 集成）

**URL**：https://smithery.ai

**步骤**：
1. 在 `lm203688/healthlens` 仓库根目录确保有 `.mcp.json` 或 `mcp-server/.mcp.json`（已创建）
2. 访问 https://smithery.ai，点 "Publish"
3. 用 GitHub OAuth 授权
4. 选择仓库 `lm203688/healthlens`
5. 选择 MCP server 入口（指向 `healthlens_agent/mcp_server.py` 或 README）
6. 提交，Smithery 自动读取元数据

**参考**：aishield 的 `mcp-server/smithery.yaml` 可作为模板。

### 4. mcp.so（P1）

**URL**：https://mcp.so

- Web 表单提交
- 与 Glama 类似信息
- 免费，无审核

### 5. PulseMCP（P1）

**URL**：https://pulsemcp.com

- Web 表单提交
- 需 GitHub 仓库
- 免费

### 6. Coze 插件市场（P2，需企业账户）

**URL**：https://www.coze.cn

- 需企业认证
- 提交插件申请
- 审核周期 3-7 天

### 7. Dify 插件市场（P2，需企业账户）

**URL**：https://dify.ai

- 需企业账户
- 提交插件 PR
- 审核周期 1-2 周

---

## 五、提交前 Checklist

### 元数据完整性
- [ ] `mcp-server/server.json` 存在且字段完整
- [ ] `mcp-server/README.md` 存在且说明清晰
- [ ] `mcp-server/.mcp.json` 存在且可复制
- [ ] `LICENSE` 文件存在（MIT）
- [ ] `pyproject.toml` 可 `pip install`

### 功能测试
- [ ] `python -m healthlens_agent mcp --demo` 正常输出
- [ ] JSON-RPC `tools/list` 返回 6 个工具（L1+L2）
- [ ] 每个工具调用返回合法 JSON
- [ ] `hl_health_check` 返回 `status: ok`

### 安全边界
- [ ] 默认 `HL_MCP_EXPOSE_PRIVATE=0`（L3 关闭）
- [ ] 每个 tool 描述含免责声明
- [ ] 无用户个人数据暴露
- [ ] GDPR 影响评估文档已就位

### 分发准备
- [ ] GitHub 仓库已公开
- [ ] PyPI 包已发布（可选但推荐）
- [ ] healthlens.cc 前端已加 MCP Available 徽章（可选）

---

## 六、上架后监控指标

上线 4 周内追踪：

| 指标 | 目标 | 追踪方式 |
|---|---|---|
| 日均 tool calls | > 100 | 后端日志 |
| 独立调用来源 | > 10 | User-Agent / caller_hash |
| Glama 排名 | Top 200 | Glama 面板 |
| Claude/Cursor 引用率 | > 5% | Google Analytics |
| MCP → healthlens.cc 转化 | > 0.1% | UTM 参数 |

**推荐**：在所有 tool 返回中加 `url: "https://healthlens.cc?utm_source=mcp"` 参数，便于追踪来源。

---

## 七、失败回滚

如果上架后发现问题（安全漏洞、数据泄露、法律纠纷）：

1. **立即** 关闭对应 tool（设置 `_EXPOSE_PRIVATE=False` 或删除 handler）
2. **同时** 在 Glama / Registry / Smithery 提交下架请求
3. **通知** 所有已知调用方
4. **审计** 事故日志，更新红线清单

---

## 八、与 Muse/Grok Bot 生态的关系

**当前状态**：Muse 和 Grok Bot 均**无第三方 MCP 接入接口**，暂无法上架。

**未来可能性**：
- 如果 Meta 决定开放 Muse MCP marketplace，我们的 server 可第一时间接入
- 如果 xAI 决定开放 Grok Bot MCP 生态，同上

**策略**：
- **不做**：主动开发 Muse/Grok 专用 SDK
- **要做**：把 server 做到"任何标准 MCP 客户端都能消费"的水平
- **验证**：6-12 个月后再评估实际流量

---

## 九、下一步（本周内）

1. [ ] 提交 PR 到 `lm203688/healthlens` main 分支
2. [ ] 提交到 Glama（< 30 分钟）
3. [ ] 提交 PR 到 Official MCP Registry（< 1 小时）
4. [ ] 提交到 Smithery（< 30 分钟）
5. [ ] 前端加 MCP Available 徽章（P2，可选）
6. [ ] 观察 2 周调用量，决定是否扩 L3
