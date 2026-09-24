# HealthLens MCP Server 设计文档

**版本**：v0.1 (2026-09-24)
**目标**：把 HealthLens 的养生知识能力作为 MCP Server 暴露给海外 Agent 生态（Claude / Cursor / Cline / Coze / 未来可能的 Muse 等），作为 wellness 领域可信知识源。

---

## 一、目标与定位

### 是什么
- **一个 Python stdio MCP Server**：`python -m healthlens_agent mcp` 启动
- **一个 wellness 知识源**：让外部 Agent 通过标准 MCP 协议查询养生知识、八轴框架解释、通用饮食/运动建议
- **一份可上架的资产**：可上架 Glama、Official MCP Registry、Smithery、Coze 插件市场

### 不是什么
- ❌ 不做用户健康数据接口（不暴露 checkin、生物年龄、个性化建议）
- ❌ 不做医疗建议（八轴推荐结果不通过 MCP 输出）
- ❌ 不做中医处方判定（十八反十九畏等安全判定保留在后端）

### 商业逻辑
```
外部 Agent 用户 → 消费 HealthLens MCP → 感知 "HealthLens 是可信 wellness 知识源"
                → 转化到 healthlens.cc（付费内容 / Pro 订阅）
```

---

## 二、分层策略（L1 / L2 / L3）

| 层 | 内容 | 数据敏感 | 默认暴露 | 触发方式 |
|:---:|---|:---:|:---:|---|
| **L1 内容层** | 养生文章、八轴框架科普、机制解释 | 无 | ✅ | 无认证 |
| **L2 知识层** | 通用饮食建议、运动建议、健康指标解读 | 无个体数据 | ✅ | 无认证 |
| **L3 用户层** | 用户 checkin、个性化建议、健康信号解读 | **高**（GDPR Art. 9） | ❌ | 需 OAuth + 用户授权 |

**MVP 范围**：仅实现 L1 + L2，共 6 个 tool。L3 保留在未来认证流完成后启用。

---

## 三、Tool 清单

### L1 内容层（4 个，公开可用）

| Tool | 参数 | 返回 | 说明 |
|---|---|---|---|
| `hl_health_check` | - | `{status, version, uptime}` | 心跳/版本检查 |
| `hl_search_knowledge` | `query: str` | 匹配文章列表 | 语义搜索养生知识库 |
| `hl_get_axis_detail` | `axis_id: A-H` | 单轴完整解释 | 八轴框架科普 |
| `hl_get_wellness_article` | `slug: str` | 完整文章 | 拿单篇 SEO 文章 |

### L2 知识层（2 个，通用建议）

| Tool | 参数 | 返回 | 说明 |
|---|---|---|---|
| `hl_suggest_general_diet` | `goal: str, preferences: list` | 通用饮食建议 | 通用推荐，无个体数据 |
| `hl_suggest_general_motion` | `intensity: str, duration_min: int` | 通用运动建议 | 通用推荐 |

### L3 用户层（未来实现，需 OAuth）

| Tool | 前置条件 |
|---|---|
| `hl_get_user_checkin` | OAuth 用户授权 |
| `hl_recommend_personalized` | OAuth + 明确同意书 |
| `hl_read_health_signal` | OAuth + 用户明确请求 |

**L3 关闭**：默认不注册任何 L3 tool。要通过环境变量 `HL_MCP_EXPOSE_PRIVATE=1` 显式开启，且必须同时设置 `HL_MCP_OAUTH_ENABLED=1`。

---

## 四、数据边界（红线清单）

以下数据**永远不通过 MCP 暴露**，任何 PR/issue 请求开放都应拒绝：

1. 用户 checkin 记录、生物年龄、八轴推荐结果
2. 用户账号、密码、支付信息、邮件订阅
3. 中医处方、十八反十九畏判定（避免医疗责任）
4. 慢病风险评估（risk_assess）——虽然技术上是简化模型，但对外暴露容易被误用为诊断
5. 融合推理的个性化推荐（fusion_engine）——同上

**理由**：MCP 调用方是任意第三方 Agent，我们无法约束其后续处理；一次数据外泄足以终结项目信誉。

---

## 五、部署方案

### 方案 A：Python stdio（MVP，本周内可交付）

```bash
# 用户安装
pip install healthlens-agent

# MCP 客户端配置（Claude Desktop / Cursor / Cline）
{
  "mcpServers": {
    "healthlens": {
      "command": "python",
      "args": ["-m", "healthlens_agent", "mcp"]
    }
  }
}
```

**优点**：符合 MCP 规范、易分发、可 npm/pip 包装
**缺点**：用户需本地装 Python + 依赖

### 方案 B：Cloudflare Worker + SSE（未来，1-2 月）

```
https://mcp.healthlens.cc/sse
```

**优点**：零客户端安装、可全球加速、易被 Muse 未来接入
**缺点**：需 Cloudflare Workers Paid plan、需 HTTPS 证书、需 OAuth 层

### 落地顺序

1. **MVP（本周）**：方案 A + Glama 上架
2. **观察 2-4 周**：看实际调用量、来源 Agent
3. **如调用量合理**：加方案 B + OAuth 认证，扩 L3

---

## 六、注册市场清单

### 立即可上（1-3 天）

| 市场 | URL | 提交方式 | 备注 |
|---|---|---|---|
| **Glama** | https://glama.ai/mcp | Web 表单 | 免费，参考 aishield 已上架 |
| **Official MCP Registry** | https://github.com/modelcontextprotocol/servers | GitHub PR | 需 fork + PR |
| **Smithery** | https://smithery.ai | GitHub 仓库配置 | 已有 aishield 先例 |
| **mcp.so** | https://mcp.so | Web 表单 | 免费 |
| **PulseMCP** | https://pulsemcp.com | Web 表单 | 免费 |

### 需付费或审核（1-2 周）

| 市场 | 备注 |
|---|---|
| **Coze 插件市场** | 需企业账户 + 审核 |
| **Dify 插件市场** | 需企业账户 |
| **LobeChat 插件** | GitHub PR |

### Muse / Grok Bot 生态

- **Muse (Meta)**：目前无第三方 MCP 接入接口，暂无法上架
- **Grok Bot (xAI)**：目前无第三方 MCP 接入接口
- **未来可能性**：如果 Meta / xAI 决定开放 MCP marketplace，我们的 server 可第一时间接入

**注意**：把"Muse 接入"当作**长期布局**而非**短期收益**。真实即期收益来自 Claude / Cursor / Cline 用户。

---

## 七、隐私与合规

### GDPR 影响

- **L1/L2**：不涉个人数据，GDPR Art. 9 不适用
- **L3**：处理健康数据 → 触发 Art. 9，需用户明确同意（Art. 7(3)）+ 数据保护影响评估（DPIA）
- **默认关闭 L3**：让 MVP 保持 GDPR-safe

### GDPR 权利映射

| GDPR 权利 | L1/L2 状态 | L3 状态（未来） |
|---|---|---|
| 访问权 | N/A | 需实现 |
| 删除权 | N/A | 需实现 |
| 数据可携带 | N/A | 需实现 |
| 反对权 | N/A | 需实现 |

### 免责声明

MCP server 所有 tool 描述中必须包含：
> "This is general wellness information, not medical advice. Consult a healthcare professional for personal health decisions."

---

## 八、错误处理与限流

### 限流

- 单用户：100 tool calls / 分钟（防止 agent 死循环刷接口）
- 全局：10,000 calls / 分钟（防止被滥用为免费 API）

### 错误码

- `200`：正常返回
- `400`：参数错误
- `404`：知识库条目不存在
- `429`：超出限流
- `503`：后端不可用

### 审计

所有 L1/L2 调用写入 `audit_events` 表（已有审计链机制），字段：
- `tool_name`, `caller_hash`, `timestamp`, `params_hash`, `response_hash`
- 只存 hash，不存原始参数（避免泄露用户 prompt）

---

## 九、监控指标

上线后 4 周内追踪：

| 指标 | 目标 | 说明 |
|---|---|---|
| 日均 tool calls | > 100 | 验证真实使用 |
| 独立调用来源 | > 10 | 不同 Agent 客户端 |
| Glama 排名 | Top 200 | 品类排名 |
| Claude / Cursor 引用率 | > 5% | 在生态中的曝光 |
| 转化率 | > 0.1% | MCP 用户到 healthlens.cc 付费用户 |

---

## 十、后续演进

- **v0.2**：加 Cloudflare Worker 部署（SSE 传输）
- **v0.3**：加 OAuth 认证层，开放 L3 部分 tool
- **v0.4**：加多语言支持（中/英/日/韩）
- **v1.0**：稳定版，考虑企业版授权

---

## 十一、决策日志

| 决策 | 时间 | 理由 |
|---|---|---|
| 只做 L1+L2，暂不开放 L3 | 2026-09-24 | GDPR 合规、避免医疗责任、避免数据外泄 |
| Python stdio 而非 CF Worker | 2026-09-24 | MVP 速度、MCP 生态兼容性 |
| 保留 fusion_engine 但不默认暴露 | 2026-09-24 | 需要个性化数据，属于 L3 范畴 |
| 不主动接 Muse/GrokBot | 2026-09-24 | 它们当前不消费第三方 MCP，接入是布局而非收益 |
