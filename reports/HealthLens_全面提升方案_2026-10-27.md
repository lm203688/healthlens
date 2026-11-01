# HealthLens 项目全面提升报告

**审计日期：** 2026-10-27  
**视角：** 数字健康领域专家、AI 项目专家、目标用户、产品与合作方  
**范围：** 产品定位、工程架构、AI 与数据、证据与安全、交互闭环、竞品、前沿趋势、商业化及 12 个月路线图  
**审计性质：** 基于仓库静态扫描、关键链路代码核验、前端构建及分组测试的技术与产品审计；不是医疗认证、渗透测试或临床有效性评价。

---

## 一、执行摘要：项目最需要的不是“更多 AI”，而是“可信地走完一次改善”

HealthLens 已经不是简单的健康问答项目。它拥有 FastAPI＋React 主应用、八轴规则引擎、中医体质与古籍知识、PGx、OCR、可穿戴设备、GraphRAG、纵向追踪、因果仿真、联邦学习适配器、多法域 Claims、MCP／A2A 等资产。代码广度和研究意识明显高于普通健康 MVP。

但当前最突出的矛盾是：**技术与研究资产显著多于产品化成熟度，能力覆盖显著快于主链路、真实证据和用户闭环的成熟速度。** 新手快速评估与完整评估存在确定性阻断，Agent 流式交互、基因组上传存在鉴权与状态问题，TOTP 登录设计存在高风险；同时，传感器基础模型仍以 dry-run 和手工特征为主，因果仿真的耦合系数未经真实因果识别，证据库真实出版验证覆盖率仅 5.8%。这些问题决定了项目下一阶段不能继续以“新增模块数量”为主要进展指标。

### 核心建议

1. **重新定位：** 从泛化的“AI 双轨诊断／精准治疗”转向 **“可验证的中西医融合个人健康实验平台”**。平台帮助用户理解数据、选择低风险健康行动、记录执行、复测变化，并清楚区分事实、规则推断、AI 解释和未验证假设。
2. **先收敛，再跃迁：** 0–2 周冻结非必要新功能，集中修复主链路、安全和跨平台测试；1–3 个月只做一个先锋场景，建议优先 **睡眠与压力恢复**，因为它有高频设备数据、短周期反馈和较低干预风险。
3. **以周期代替报告收费：** 从“一次生成健康报告”升级为“8–12 周可验证改善周期”。用户购买的不是更多文字，而是目标设定、轻量行动、依从支持、复测和可解释变化。
4. **建立四层证据体系：** 确定性安全规则、真实出版证据、个人纵向证据、外部人群验证分别管理，任何一层都不能冒充另一层。
5. **将前沿技术变成有门槛的期权：** PPG 基础模型先做公开基准与人工特征对照；联邦学习先有多机构真实数据；数字孪生先有个体动态模型和外部验证。未达到门槛前，不以概念命名能力。

### 综合评分：6.3／10

这是本次审计按下列权重形成的内部主观评分，用于资源排序，不是外部评级。

| 维度 | 权重 | 得分 | 判断 |
|---|---:|---:|---|
| 领域资产与差异化 | 15% | 8.0 | 中西医融合、八轴、古籍与安全规则有辨识度 |
| 技术架构与工程广度 | 15% | 7.5 | 模块丰富、后端测试规模大，但文档与前端质量治理滞后 |
| AI 与智能化成熟度 | 15% | 6.8 | 多 Agent、GraphRAG、仿真和适配器完整，真实学习与验证不足 |
| 互动性与用户闭环 | 15% | 4.5 | 有目标、打卡、追踪零件，但关键旅程存在断点，信息架构分散 |
| 数据与证据可信度 | 15% | 4.8 | 诚实披露较好，真实出版证据和真实人群验证不足 |
| 安全、隐私与合规 | 10% | 5.0 | 有法域、Claims、急救规则基础，TOTP 与本地敏感存储需优先整改 |
| 实用性与商业闭环 | 10% | 6.2 | B2B2C 接口具潜力，核心价值尚未收敛成可购买结果 |
| 前沿发展定位 | 5% | 8.0 | 方向覆盖前沿，但应建立能力命名和验证门槛 |
| **加权总分** | **100%** | **6.26≈6.3** | **研究型平台基础较强，产品可信闭环是当前短板** |

---

## 二、审计事实底座与能力分层

### 2.1 本次扫描得到的规模事实

| 项目 | 本次静态扫描结果 | 含义 |
|---|---:|---|
| 后端 `app` | 231 个 Python 文件，56,507 行 | 已是大型服务端，而非轻量实验脚本 |
| 前端 `frontend/src` | 37 个 JS／JSX 文件，7,988 行 | 页面已较多，设计系统与测试投入不足 |
| `tests` | 117 个文件，26,026 行；AST 静态识别 1,959 个同步／异步测试函数 | 后端测试资产可观，但不能替代端到端用户旅程 |
| `healthlens_agent` | 37 个文件，6,125 行 | 独立 Agent 体系已形成 |
| HTTP 方法装饰器端点 | 325 个，分布于 58 个模块 | 接口丰富，也带来导航、权限、运维与契约治理复杂度 |
| GraphRAG 当前缓存 | 1,661 节点、2,005 边、6 个来源 | 已有图遍历基础，不等同完整语义向量 RAG |
| 包版本 | `pyproject.toml` 为 0.37.0 | README 的 v0.25.0、模型卡的 v0.34.1 已漂移 |

版本事实见项目元数据；README 同时仍使用“诊断、精准治疗、生产就绪、174 个测试全绿”等旧口径，容易使用户、合作方和评审者产生错误预期。[pyproject](kimi-cite://text?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cpyproject.toml&text=version%20%3D%20%220.37.0%22 "citation") [README](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5CREADME.md&line=14&text=**v0.25.0** "citation")

### 2.2 三层能力台账：对外表达必须按层管理

| 层级 | 当前资产 | 可以怎样说 | 不应怎样说 | 升级条件 |
|---|---|---|---|---|
| **A．已形成产品／规则能力** | 八轴确定性评分、缺失轴状态、中医规则、证据标签、Claims、多法域、目标／打卡／纵向接口、MCP 工具 | “规则驱动、边界明确的健康管理与研究平台” | “AI 已证明能改善疾病” | 修通旅程、完成真实使用测试、持续监测 |
| **B．可运行但尚未完成外部验证** | GraphRAG 图遍历、反事实仿真、可靠性电池、合成档案、跨仪器桥接、PGx／OCR 流程 | “研究原型／仿真工具／待验证假设” | “临床数字孪生”“已证实因果效果” | 真实数据校准、外部验证、专家审查、误差分层 |
| **C．前沿技术期权与集成脚手架** | Pulse-PPG／PaPaGei 适配器、联邦学习适配器、可选重型科学依赖 | “已预留标准接口与实验入口” | “已接入传感器基础模型”“具备联邦医疗网络” | 真实权重、基准收益、数据合作方、隐私威胁模型、运维责任 |

模型卡明确写明当前是固定阈值规则、没有训练权重，真实人群区分度未验证，并把 30–60 人、8–12 周前瞻队列列为改进事项；ICC 0.957–1.000 等结果属于既定评估电池的可靠性结果，不能外推为临床有效性。[model_card](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cdocs%5Cmodel_card.md&line=22&text=no%20trained%20ML%20model%2C%20no%20learned%20weights "citation")

传感器适配器也明确说明真实权重待接入，默认是 dry-run，fallback 为 20 维手工特征；这适合作为基线，不应包装为基础模型推理。[sensor_adapter](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Capp%5Clib%5Csensor_adapter.py&line=117&text=%23%20真实%20Pulse-PPG%20/%20PaPaGei%20模型待用户提供权重时接入。 "citation") 因果层同样承认耦合系数是透明启发式、非因果识别量。[causal_simulator](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Capp%5Clib%5Ccausal_simulator.py&line=79&text=耦合系数为透明启发式（文献锚定），**非因果识别量**，须经前瞻队列标定。 "citation")

---

## 三、P0：影响可用性与信任的关键问题

下表是代码证据支持的缺陷判断；是否已在某次部署中复现，还应由端到端测试和真实环境日志补充确认。

| 优先级 | 问题与证据 | 用户／安全影响 | 必须落地的修复与验收 |
|---|---|---|---|
| **P0** | 快速引导按 `answers[q.key]` 写入，却按 `answers[i]` 读取，见 `Onboarding.jsx:89,94,100–102,142` | 三题完成后仍可能无法提交，首启价值无法交付 | 统一 key 读取；Vitest 覆盖三种答案组合，Playwright 验证从首题到预览完整可达。[Onboarding](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Cpages%5COnboarding.jsx&line=94&text=const%20chosen%20%3D%20QUICK_QUESTIONS.filter((_%2C%20i)%20%3D%3E%20answers%5Bi%5D)%3B "citation") |
| **P0** | 完整评估 `submit()` 定义于 `HealthAssess.jsx:45`，开始按钮在 149 行仅 `setStep(2)` | 页面停在“分析中”，实际未发起分析 | 按钮调用真实提交并管理错误／重试；mock 成功、400、500、超时四种路径，结果页必须出现。[HealthAssess](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Cpages%5CHealthAssess.jsx&line=149&text=onClick%3D%7B()%20%3D%3E%20setStep(2)%7D "citation") |
| **P0** | SSE 有任一事件后在 `AgentChat.jsx:184` 直接返回，绕过 258 行复位；400 fallback 在 198 行再次加入用户消息 | 对话可能长期 loading；异常时重复用户消息 | 用 `try/finally` 统一清理，消息只写入一次；测试流完成、空流、中途断流、400 与网络错误。[AgentChat](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Cpages%5CAgentChat.jsx&line=184&text=if%20(gotAny)%20return%3B "citation") |
| **P0** | `client.js:53–58` 流式请求和 96 行基因上传绕过统一 `request()`，没有附带本地 Bearer；基因后端在 `genome.py:69–74` 强制登录 | 流式接口可能持续 401 并降级，基因上传可能直接失败 | 统一认证请求工厂；表单请求不错误设置 JSON Content-Type；用已登录浏览器验证 SSE 和 VCF／23andMe 上传。[client](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Capi%5Cclient.js&line=96&text=genomeUpload%3A%20(formData)%20%3D%3E%20fetch(%60%24%7BAPI_BASE%7D%2Fgenome%2Fupload%60%2C%20%7B%20method%3A%20%27POST%27%2C%20body%3A%20formData%20%7D)%2C "citation") [genome](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Capp%5Capi%5Cgenome.py&line=73&text=current_user%3A%20User%20%3D%20Depends(get_current_user)%2C "citation") |
| **P0 安全** | `/totp/verify` 在 `auth.py:467–497` 仅凭 6 位码遍历全部启用 TOTP 的用户并直接签发 token，没有账号或第一因素 | TOTP 被设计成独立登录因素；多用户遍历、碰撞、猜测与账号定位都增加风险 | 改成“账号＋第一因素→短时挑战→TOTP”的第二因素流程；按账号、IP、设备限流，挑战一次性且短时有效，记录审计与恢复流程；安全评审后才重新开放。[auth](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Capp%5Capi%5Cauth.py&line=482&text=result%20%3D%20await%20db.execute(select(User).where(User.totp_enabled%20%3D%3D%20True))%20%20%23%20noqa%3A%20E712 "citation") |
| **P0 质量** | 本机 Windows 分组测试出现 19 个失败，集中于 GBK 解码子进程输出 | 跨平台贡献者和发布结果不可复现 | 子进程统一 `encoding="utf-8"`、`errors="replace"`，必要时设置 `PYTHONIOENCODING=utf-8`；增加 Windows CI 与 Linux CI 双门禁 |

### 安全与隐私的同步整改

- **敏感数据最小化。** token 和健康对话使用 `localStorage`，会放大 XSS、共享设备和浏览器持久化风险；聊天存储代码明确将历史写入该位置。[chatStore](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Clib%5CchatStore.js&line=39&text=localStorage.setItem(STORE_KEY%2C%20JSON.stringify(trimmed))%3B "citation") 优先采用安全的服务端会话或 `HttpOnly`、`Secure`、合理 `SameSite` Cookie，并配合 CSRF 设计；敏感聊天默认不持久化，提供独立健康空间、自动过期、导出与彻底删除。
- **不要把“缓存可用”误当“隐私安全”。** Service Worker 只拦截 `/app/api/`，而客户端实际 API 根是 `/api/v1`，路径策略不一致；健康数据也不应简单进入通用 Cache Storage。[sw](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Cpublic%5Csw.js&line=40&text=if%20(request.method%20%3D%3D%3D%20%27GET%27%20%26%26%20url.pathname.startsWith(%27%2Fapp%2Fapi%2F%27))%20%7B "citation") 建立缓存白名单：公开静态资源可缓存，健康、基因、聊天和鉴权响应默认不缓存。
- **纵深安全。** 在已有急救规则和 Claims 之外，补充 CSP 与依赖扫描、上传内容／大小／格式隔离、基因数据区域驻留验证、字段级加密、密钥轮换、管理员操作审计、导出授权与撤销、日志去标识化。
- **外部安全验证。** 本轮不是渗透测试。P0 修复后应另做认证矩阵、越权、限流、重放、文件上传和 XSS 专项测试。

---

## 四、从产品专家与用户角度：重建一条能完成、能理解、愿意回来的旅程

### 4.1 当前体验问题不是“页面不够漂亮”，而是任务结构不闭环

桌面导航一次列出 16 个入口，用户需要自行理解“评估、体质、脉搏、八轴、打卡、变化、报告、知识、Agent”之间的关系。[App](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5CApp.jsx&line=24&text=const%20NAV_ITEMS%20%3D%20%5B "citation") 上传结果和 PGx 仍直接展示 JSON，这对开发者有用，对普通用户则意味着“系统把解释工作推回给我”。[Upload](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Csrc%5Cpages%5CUpload.jsx&line=174&text=%3Cpre%20className%3D%22mt-4%20text-xs%20bg-slate-50%20rounded%20p-3%20overflow-auto%20max-h-64%22%3E "citation")

### 4.2 将 16 个功能入口重组为四个用户任务

1. **今天：** 今日状态、一个最重要变化、一个可执行行动、需要关注的风险；不先展示复杂雷达和模型角色。
2. **我的实验：** 目标、基线、干预、执行记录、复测、变化解释；纵向追踪成为主角。
3. **我的数据：** 设备、报告、基因、档案、授权、来源、更新时间和删除入口。
4. **专业支持：** 知识证据、中医解释、合作方工具、分享与付费，不再与主任务平级争抢注意力。

Agent 不是第五个孤立页面，而是贯穿四个任务的解释与操作层。用户可以直接对“为什么这周睡眠效率下降”提问，Agent 调用受控工具、引用实际数据，并提供“创建两周规律作息实验”按钮；所有写入操作需用户确认。

### 4.3 先锋场景：睡眠与压力恢复的 8 周闭环

| 阶段 | 用户看到什么 | 系统做什么 | 完成标准 |
|---|---|---|---|
| 建立基线 | 近 14 天睡眠、HRV、主观精力与压力，缺失数据明确标注 | 统一时间、单位和来源；计算个人基线而非只看人群阈值 | 数据覆盖率可见，用户确认目标 |
| 共同制定计划 | 最多 1–2 个低风险行为杠杆，如固定起床时间、减少晚间咖啡因 | 规则排除禁忌，AI 只做解释和个性化表达 | 用户主动确认，不自动执行高风险建议 |
| 每日轻互动 | 10–30 秒打卡、异常提醒、可跳过 | 依从记录与数据质量检测，避免过度提醒 | 用户能暂停、撤销、修改 |
| 每周复盘 | 一张趋势图、一个变化、一个下一步 | 区分数据变化、相关性和推测，不把波动写成疗效 | 明确“未测量／样本不足／不确定” |
| 第 8 周复测 | 与自身基线比较、目标完成度、下个周期建议 | 预注册主要指标，校正多重比较，保留不良体验 | 形成完整可导出改善周期 |

**为什么不是同时做代谢：** 代谢与慢病管理很有价值，但检验周期、临床风险、指标解释和监管要求更高。建议先把睡眠／压力闭环做到高完成率，再复用同一实验引擎扩展代谢。

### 4.4 结果表达采用“四层卡片”

每一条结论都分为：**观察到的数据→规则／模型如何解释→建议采取什么→证据和不确定性是什么。** 分数旁显示数据完整度、来源、测量时间和上次变化；合成数据不得出现在真实用户证据计数中。原始 JSON 收进“开发者详情”，用户主视图使用指标表、来源标签、趋势图和可执行按钮。

---

## 五、AI 与技术架构提升：从“角色编排”走向“可验证任务系统”

### 5.1 建立统一 Health Context，而非继续扩张 Agent 数量

建议新增一个版本化、权限化的个人健康上下文层，作为评估、对话、纵向追踪和合作方接口的共同底座：

```text
设备／报告／问卷／基因／古籍知识
              ↓
数据质量、单位标准化、时间对齐、来源与同意
              ↓
Versioned Health Context（事实 + 缺失 + 冲突 + 权限）
              ↓
确定性安全规则 → 八轴与中医推理 → 受控工具调用 → 个性化解释
              ↓
目标与实验 → 依从追踪 → 复测 → 个人证据更新
```

- **数据语义：** FHIR 管 Patient、Observation、DiagnosticReport、Consent、Provenance 等交换语义；项目内部再保留八轴和中医扩展 Profile。
- **工具语义：** MCP 暴露只读检索、指标计算、实验创建草稿等可审计工具，按用户和数据域授权。
- **协作语义：** A2A 用于确有跨组织、长任务需求的 Agent 协作，不为展示角色而增加网络跳点。
- **写入治理：** 所有改变目标、计划、分享和权限的动作采用“草稿→用户确认→审计提交”，高风险工具不可由模型直接执行。

前沿 Agent 评价应看端到端成功率、规则遵循、工具调用正确率和人工接管，而不是“Planner／Executor／Critic／Referee”的数量。Stanford HAI 2026 报告显示，前沿模型在多轮工具与规则任务上的 pass@1 仍约 62.9%–70.2%，说明演示成功不等于可靠任务自动化。[Stanford HAI](kimi-cite://web?url=https%3A%2F%2Fhai.stanford.edu%2Fassets%2Ffiles%2Fai_index_report_2026.pdf "citation")

### 5.2 GraphRAG：先建立可核验检索，再谈复杂推理

当前图缓存和 BFS／最短路径适合解释“证候—轴—通路—古籍”的关系，但还应补齐：

1. 文档 chunk、出版信息、原文位置、图节点和推荐结果之间建立稳定引用 ID。
2. 关键词、向量与图遍历做混合召回；按任务建立 gold set，分别测召回率、引用正确率、答案忠实度和拒答。
3. 每个答案返回证据状态：已核验出版、传统文本、未核验、合成测试；合成条目永不进入用户答案证据。
4. 古籍内容区分“历史原文”“现代解释”“当代临床证据”，避免把古籍记载自动升级为疗效证明。
5. 图更新采用版本与审批，不允许 Agent 在对话中直接修改受控医学知识。

### 5.3 传感器基础模型：以“增益证据”决定接入，而非以模型名称决定路线

PaPaGei 展示了生理信号基础模型的潜力：其公开工作使用 57,000 小时、2,000 万 PPG 片段，并在多项下游任务上报告分类和回归性能提升。[ICLR](kimi-cite://web?url=https%3A%2F%2Ficlr.cc%2Fvirtual%2F2025%2Fposter%2F28573 "citation") [PaPaGei](kimi-cite://web?url=https%3A%2F%2Fgithub.com%2Fnokia-bell-labs%2Fpapagei-foundation-model "citation") 但 HealthLens 不应直接据此承诺自身收益。

**落地顺序：**

- 固定当前 20 维手工特征为 baseline，统一信号质量、窗口、采样率和缺失处理。
- 在公开 PPG 数据集上比较“手工特征＋小模型”“真实 PaPaGei／Pulse-PPG 编码器＋线性探针”“端到端微调”。
- 按设备、肤色可获取时代理变量、年龄、性别、运动状态和信号质量分层，报告校准和失败率。
- 只有在目标指标、延迟、能耗和跨设备稳定性超过预设门槛后，才进入真实产品；否则保留小模型。
- 边缘端采用量化、蒸馏和按需推理，原始波形默认本地处理，云端只上传经授权的特征或摘要。

### 5.4 因果仿真与数字孪生：先叫“实验引擎”，用验证赢得更名权

数字孪生的前沿价值在于由真实纵向数据驱动个体动态模型和反事实，但可信性依赖外部验证，而不是有 SCM 图和轨迹动画。[Nature Biomedical Engineering](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs41551-026-01733-4.pdf "citation") [Nature Reviews Methods Primers](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs43586-025-00454-3 "citation")

建议分三级：

1. **当前：个人基线＋n-of-1 实验引擎。** 记录基线、干预、依从和结果，输出观察变化，避免“干预造成了变化”的强因果措辞。
2. **中期：校准个体动态模型。** 使用真实纵向数据估计参数，报告预测区间、留出时间段误差、外部个体误差和敏感性。
3. **长期：经验证的个人数字孪生。** 只有在预设任务上持续预测准确、反事实经前瞻验证、适用边界明确后使用此名称。

### 5.5 OCR、PGx 与小模型：优先做“可纠正的数据入口”

- OCR 从“识别全文”升级为“表格结构＋指标＋单位＋参考区间＋页码位置”的字段级置信度；低置信字段必须人工确认，保留原图对照。
- 建立真实脱敏报告测试集，按医院版式、拍照角度、语言、手写、表格密度分层；指标级错误比整页字符准确率更重要。
- PGx 只展示经审核的变异、来源、适用人群和限制；不自动给剂量，不把基因型直接翻译为治疗建议。
- 多模态大模型可作为 OCR 候选解释器，但必须由词典、单位、参考区间和确定性校验约束，原始值以用户确认为准。
- Stanford HAI 对小型任务专用模型在部分基因组任务上的优势提示：专用小模型、规则和检索可以是比“更大通用模型”更经济可靠的路线。[Stanford HAI Medicine](kimi-cite://web?url=https%3A%2F%2Fhai.stanford.edu%2Fassets%2Ffiles%2Fai_index_report_2026_chapter_6_medicine.pdf "citation")

---

## 六、数据、证据、安全和合规：把“诚实披露”升级为“可运行治理”

### 6.1 证据库需要从“数量指标”转向“可用证据覆盖”

模型卡记录 120 条证据中 7 条 Crossref 验证、8 条传统文本、14 条未验证、91 条合成验证，真实出版验证覆盖为 7／120＝5.8%。[model_card](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cdocs%5Cmodel_card.md&line=80&text=Evidence%20DB%20verified%20coverage%20|%207%20verified%20%2F%20120%20total%20%3D%205.8%25%20(4%20L1%20%2B%203%20L2%20via%20Crossref)%3B%20%2B8%20traditional-text%2C%20%2B14%20unverified_no_publication%2C%20%2B91%20synthetic_validation "citation")

**建议不是机械补齐 120 条 DOI，而是按实际推荐覆盖率治理：**

- 建立“每条线上建议→至少一条适用证据或明确传统经验标签”的反查表。
- DOI 解析通过只证明出版存在，还需结构化提取研究对象、干预、对照、结局、效应、局限和与本场景的适用性。
- 设置证据所有人、复审日期和撤回机制；证据更新触发受影响建议回归测试。
- 将传统医学文献单列，不与 RCT、指南、系统综述混算。
- 对外指标改为“活跃推荐的真实证据覆盖率”“高影响建议专家审核率”“过期证据比例”，而不是数据库总条数。

### 6.2 真实验证的最小可行设计

模型卡建议 30–60 人、8–12 周前瞻队列，这适合作为首轮可行性与测量研究，**不是最终临床验证**。[model_card](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cdocs%5Cmodel_card.md&line=155&text=1.%20**Real%20prospective%20cohort%20(D5).**%20Enrol%2030-60%20subjects%20on%20their%20own "citation")

首轮研究建议：

1. 预注册主要任务：数据连接成功率、8 周留存、计划完成、复测完成、轴评分重测信度和与既有量表的一致性。
2. 睡眠／压力场景同步采集既有量表、设备原始指标、主观打卡和依从；保存设备型号与固件。
3. 预设缺失、异常、停用、不良体验和退出规则；按年龄、性别、设备等分层报告，不只给总体均值。
4. 将 20 个 case＋2 个 control 的验证档案视作工程样本，额外补充真正有区分力的阴性、边界、冲突和共病对照。[engine_validation_metrics](kimi-cite://text?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cengine_validation_metrics.json&text=%22n_case%22%3A%2020 "citation")
5. 第二阶段再做有对照、足够功效计算的效果研究；不要从首轮可行性样本直接推导疗效。

合成数据适合测试边界、 pipelines 和故障，不应替代真实结局。相关方法研究也强调 train-on-synthetic／test-on-real，并分别评估效用和隐私风险。[Scientific Reports](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs41598-024-72894-y "citation")

### 6.3 将监管准备做成持续工程资产

WHO 对医疗健康大模型的治理建议强调明确任务、早期利益相关者参与、红队、发布后审计和按人群评估影响。[WHO](kimi-cite://web?url=https%3A%2F%2Fwww.who.int%2Fnews%2Fitem%2F18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models "citation") FDA 的 AI 医疗器械路径强调全生命周期、真实世界性能，以及通过 PCCP 管理计划内模型修改。[FDA](kimi-cite://web?url=https%3A%2F%2Fwww.fda.gov%2Fmedical-devices%2Fdigital-health-center-excellence%2Fartificial-intelligence-enabled-medical-devices "citation") [FDA PCCP](kimi-cite://web?url=https%3A%2F%2Fwww.fda.gov%2Fregulatory-information%2Fsearch-fda-guidance-documents%2Fmarketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence "citation")

**落地为六份持续更新的机器可读资产：** 用途与禁用场景、模型／规则卡、数据谱系与同意、风险与控制矩阵、分群性能与真实世界监测、版本变更与回滚记录。Claims 引擎应与每次发布绑定：营销文案、界面文案、模型能力和证据版本一致，避免“代码是 wellness，首页却承诺诊断治疗”。

欧盟 AI Act 的时间表仍存在调整，不能沿用旧的确定日期；应以具体用途分类和最新官方文本为准，同时提前建设数据治理、人类监督、日志、技术文档和稳健性。[European Commission](kimi-cite://web?url=https%3A%2F%2Fdigital-strategy.ec.europa.eu%2Fen%2Ffaqs%2Fnavigating-ai-act "citation") [EU 2026](kimi-cite://web?url=https%3A%2F%2Feur-lex.europa.eu%2Flegal-content%2FEN%2FTXT%2FHTML%2F%3Furi%3DCELEX%3A52026DC0234 "citation")

---

## 七、竞品启示：不要复制入口，要补齐信任与持续价值

以下仅比较公开产品叙事与本次审计可见能力，不代表竞品临床效果判断。

| 产品 | 公开优势 | 对 HealthLens 的威胁 | HealthLens 应吸收什么 | 不应复制什么 |
|---|---|---|---|---|
| **ChatGPT Health** | 独立健康空间、隔离记忆、病历与健康应用连接、授权控制、隐私承诺 | 通用对话体验和数据入口强 | 健康空间、逐次授权、记忆查看／删除、回答与来源绑定 | 不做另一个泛健康聊天框 |
| **Function Health** | 160+ 检测、每年两次、医生审核结果、个性化方案和趋势；公开价格 $365／年 | “检测—解释—复测”价值容易理解 | 把服务包装为明确周期，专业审核形成信任 | 不在缺乏服务网络时拼检测数量 |
| **Superpower** | 检测、AI 方案、照护、数据 vault、复测组合 | 整体会员体验完整 | 统一健康档案和持续服务，不卖孤立报告 | 不盲目堆会员权益或补剂商城 |
| **Oura Advisor** | 长期趋势、图表、目标计划、可删除记忆，并发展女性健康等专用能力 | 高频、低摩擦、个人纵向数据强 | 个人基线、主动但克制的洞察、人群专长包 | 不复制硬件；先做跨设备质量治理 |
| **Google Health Coach** | 主动 Today 洞察、周计划、病历摘要，统一可穿戴与健康平台；公开 SHARP 评价思路 | 生态入口、主动教练和规模化评价强 | Today 首页、周计划、评价框架、跨源同步 | 不依赖大平台流量假设，不做过宽医疗承诺 |

ChatGPT Health 的独立空间与隔离记忆说明“健康数据如何被记住和授权”已经成为核心产品功能，而非设置页附属项。[OpenAI](kimi-cite://web?url=https%3A%2F%2Fopenai.com%2Findex%2Fintroducing-chatgpt-health%2F "citation") [OpenAI Health](kimi-cite://web?url=https%3A%2F%2Fopenai.com%2Findex%2Fhealth-in-chatgpt%2F "citation") Function 的公开流程和价格说明，用户能理解的是持续检测和专业审核组成的年度服务。[Function Health](kimi-cite://web?url=https%3A%2F%2Fwww.functionhealth.com%2Fpricing "citation") [Function How It Works](kimi-cite://web?url=https%3A%2F%2Fwww.functionhealth.com%2Fhow-it-works "citation") Oura 把长期趋势、目标与可删除记忆结合，并引入临床专家参与的专用模型，体现“个人纵向状态＋专长包”的方向。[Oura](kimi-cite://web?url=https%3A%2F%2Fouraring.com%2Fblog%2Foura-advisor%2F "citation") [Oura Support](kimi-cite://web?url=https%3A%2F%2Fsupport.ouraring.com%2Fhc%2Farticles%2F39512345699219-Oura-Advisor "citation") Google 则把主动洞察、周计划、统一数据和评价框架组合成健康教练，而非只做问答。[Google Health Coach](kimi-cite://web?url=https%3A%2F%2Fblog.google%2Fproducts-and-platforms%2Fproducts%2Fgoogle-health%2Fgoogle-health-coach%2F "citation") [Google Health App](kimi-cite://web?url=https%3A%2F%2Fblog.google%2Fproducts-and-platforms%2Fproducts%2Fgoogle-health%2Fgoogle-health-app%2F "citation") Superpower 的公开产品也采用检测到持续照护与复测的组合。[Superpower](kimi-cite://web?url=https%3A%2F%2Fsuperpower.com%2F "citation")

### HealthLens 真正可建立的护城河

1. **中西医融合语义与安全规则：** 不是把两套文本并排，而是能解释映射、冲突、缺失和禁忌，并由专家持续审核。
2. **多法域 Claims／同意／审计：** 把合规执行嵌入每次建议、工具调用、分享和发布，形成 B2B 合作信任。
3. **个人纵向数据与 n-of-1 实验：** 用户自己的基线、执行和复测形成迁移成本，也形成最有价值的数据资产。
4. **Powered-by 工具层：** 向保险、企业健康、体检与健康管理机构输出受控 MCP 工具和可嵌入实验引擎，比正面争夺通用助手入口更现实。
5. **未来期权：** 传感器基础模型、联邦学习和数字孪生，只有满足前述验证门槛后才转为护城河。

---

## 八、未来 12–36 个月的前沿定位与机会清单

### 8.1 趋势—动作映射

| 前沿趋势 | 对项目的实际意义 | 现在做什么 | 暂不做什么 |
|---|---|---|---|
| Agent 从聊天转向受控执行 | 价值在完成任务且可审计 | 统一工具契约、确认写入、端到端成功评价 | 增加角色和复杂辩论 |
| 个人健康记忆与主动教练 | 留存来自长期上下文和适时行动 | 可查看／删除记忆、Today、周计划、提醒偏好 | 默认永久记忆和过度打扰 |
| 生理信号基础模型 | 可提升跨任务表征与小样本效率 | 公开基准、真实权重、人工特征消融 | 无基线对比直接上重模型 |
| 多模态医疗文档理解 | 报告结构化质量决定后续推理上限 | 字段置信度、原图定位、人工校正 | 让模型自由猜指标 |
| 个人纵向模型与数字孪生 | 从静态评分走向时间维度 | n-of-1 实验、动态预测、外部验证 | 把启发式反事实称为临床预测 |
| 隐私计算与边缘智能 | 原始敏感数据少出域 | 数据最小化、本地特征、威胁模型 | 无合作方时先建联邦平台 |
| 协议化健康生态 | 工具和数据可嵌入合作方 | FHIR 语义、MCP 工具、A2A 长任务 | 为协议数量做展示工程 |
| 持续监管与真实世界评价 | 上线只是验证开始 | 版本化模型卡、漂移与投诉监测、回滚 | 一次性合规文档 |
| 小模型与专用模型复兴 | 更低成本、更可控、更易端侧运行 | 按任务选最小足够模型，测单次成本 | 所有任务绑定最大通用模型 |

### 8.2 十二个可执行机会包

成本为粗略人周量级建议，需按团队实际人员与外部合作重新估算；“收益”均须通过指标验证。

| ID | 机会与行动 | 技术／业务抓手 | 验收标准 | 建议成本 |
|---|---|---|---|---:|
| **O1** | **主链路止血。** 修复快速评估、完整评估、SSE、基因上传与消息状态 | React 状态机＋统一请求工厂＋Vitest／Playwright | 五条核心旅程在 Chrome 移动／桌面通过；错误可恢复；无重复消息 | 2–4 人周 |
| **O2** | **认证与敏感数据整改。** TOTP 第二因素化，重审 token、聊天、缓存和分享 | 短时挑战、限流、审计、会话安全、缓存白名单 | 权限矩阵与重放测试通过；敏感数据无非必要持久化；专项安全复核 | 3–6 人周 |
| **O3** | **一个 Today。** 合并分散首页、评估和打卡，突出一个状态与一个行动 | Health Context＋任务式信息架构＋事件埋点 | 新用户无需说明即可完成“连接→理解→创建计划”；导航任务测试达标 | 4–8 人周 |
| **O4** | **8 周睡眠实验 MVP。** 把目标、依从、纵向和周报组装成一个产品 | 实验模板、基线、复测、依从和缺失管理 | 试点用户可完整结束并导出周期；主要指标预注册 | 6–10 人周 |
| **O5** | **证据可信层。** 清理推荐证据，显示来源、适用性和不确定性 | Evidence Registry、版本审批、推荐反查、gold set | 100% 活跃推荐有状态标签；高影响建议均有真实来源或明确传统经验标签 | 6–12 人周＋专家 |
| **O6** | **真实前瞻性试点。** 30–60 人、8–12 周，仅评估可行性、信度和一致性 | 预注册、同意、设备／量表同步、分群分析 | 数据字典、统计分析计划和去标识数据齐全；不输出超设计疗效结论 | 10–20 人周＋研究成本 |
| **O7** | **GraphRAG 可核验化。** 混合检索、引用定位、忠实度与拒答评价 | chunk／节点／建议稳定 ID、检索 gold set、版本化图 | 引用可回溯；合成证据零泄漏；不合格查询可拒答 | 5–9 人周 |
| **O8** | **OCR 可校正工作台。** 字段级结构化与低置信确认 | 版面模型＋指标词典＋单位校验＋原图定位 | 建立版式分层测试集；关键字段错误可见、可纠正、可回放 | 5–10 人周 |
| **O9** | **PPG 编码器实证。** 真实权重接入前先证明增益 | PaPaGei／Pulse-PPG adapter、线性探针、消融、端侧基准 | 预设指标超过手工 baseline；跨设备与低质量信号不显著退化 | 8–16 人周 |
| **O10** | **Powered-by 合作试点。** 不卖通用 Agent，卖可审计工具和改善周期 | MCP 只读工具、租户隔离、FHIR 导出、白标周报 | 1 家设计伙伴完成真实工作流；权限、延迟、成本和审计达标 | 6–12 人周 |
| **O11** | **评价与可观测平台。** 把测试从函数级扩展到任务和人群 | 离线 gold set、线上质量抽样、漂移、成本、反馈与回滚 | 每次发布有任务成功、安全召回、延迟和成本门禁；事故可定位版本 | 5–9 人周 |
| **O12** | **联邦与数字孪生期权。** 只在数据和验证成熟后升级 | 多机构协议、隐私威胁模型、动态模型、外部验证 | 至少两个真实机构／数据域；联邦优于合法集中或本地基线；孪生通过前瞻验证 | 12–30＋人周 |

### 8.3 优先级判断：哪些事情明确暂缓

- 暂缓增加新的轴、新的大类首页、新 Agent 角色和更多付费权益，直到主旅程与先锋周期达标。
- 暂缓自建通用大模型和自建可穿戴硬件；资源应投向数据质量、专用评价和差异化语义。
- 暂缓以“临床诊断、精准治疗、数字孪生、因果效果、生产就绪”为对外卖点，直到相应证据和法规路径成立。
- 暂缓以联邦学习解决“当前没有足够真实数据”的问题；联邦只解决数据不能集中的一部分问题，不创造标签、代表性和临床真值。

---

## 九、实施路线图：30／60／90 天与 12 个月

### 第 0–30 天：恢复“可用、可测、可相信”

- 第 1–2 周完成 O1、O2 的最危险部分；TOTP 在修复前限制或停用独立登录通道。
- 建立前端 Vitest／React Testing Library 与 Playwright；`package.json` 补齐 lint 实际依赖，去掉 `--fix` 作为唯一 CI lint 行为。
- 五条 E2E 旅程进入 CI：注册／登录、三题首启、完整评估、SSE／fallback 对话、报告与基因上传。
- Windows 子进程编码统一，Linux＋Windows 双 CI；失败测试按编码问题和产品问题分开管理。
- 发布“能力真实性清单”，同步 README、模型卡、官网和 API 文案；建立版本一致性检查。
- **阶段出口：** 新用户能完成核心流程，无已知 P0 阻断；认证设计通过专项复核；CI 可重复。

### 第 31–60 天：收敛成“一个场景、一个首页、一个周期”

- 上线 Today 和四任务导航，保留旧页面的深层链接，避免一次性破坏用户习惯。
- 完成睡眠／压力实验模板、14 天基线、每周复盘、8 周复测和退出流程。
- 结果页改为四层卡片；原始 JSON 收进开发者详情；缺失与低置信不再显示成 0 分。
- 建立 Evidence Registry 第一版，优先审核所有活跃推荐，而不是平均处理全部历史条目。
- **阶段出口：** 试点用户可以无需运营人员手工介入完成一个周期；所有线上建议能解释来源和状态。

### 第 61–90 天：用真实使用证据决定下一笔技术投入

- 启动 30–60 人前瞻性可行性试点，完成伦理／同意、数据管理和统计分析计划。
- 建立 Agent 任务 gold set、引用忠实度、安全召回、工具正确率、延迟和单次成本看板。
- 启动 OCR 字段级测试集与 PPG 公开基准，不等待重型模型结果才改善主产品。
- 与 1 家健康管理／企业健康设计伙伴验证 Powered-by 工具和 8 周周期，不先追求大规模渠道。
- **阶段出口：** 形成首份真实世界报告，明确哪些轴、推荐和设备特征有证据，哪些应降级或移除。

### 3–6 个月：扩展已证明的能力

- 依据 PPG 基准结果决定是否进入端侧编码器试点；依据 OCR 字段错误决定多模态模型投入。
- 完成 GraphRAG 混合召回和引用回归门禁，扩展中医专长包，邀请中医与临床专家参与高风险内容审核。
- 将一个先锋场景复用到第二个场景前，必须证明实验模板、依从和复测机制不是只对单一人群有效。
- 商业化采用“机构平台费＋完成周期服务包”试点，用户端提供基础数据管理和付费改善周期。

### 6–12 个月：从健康工具升级为可信实验网络

- 建立多版本模型／规则、证据和 Claims 的持续发布体系，支持变更影响分析和回滚。
- 有至少两个真实机构／数据域、明确隐私收益和充分运维能力后，再开展联邦学习试点。
- 只有在动态模型留出预测和前瞻反事实验证达标后，才将“个人实验引擎”升级为“数字孪生”。
- 将用户授权的可复用实验协议、真实世界评价工具和中医语义包发展为合作方标准能力。

---

## 十、指标体系：让团队为“完成改善”负责，而不是为“生成内容”负责

### 北极星指标

**每活跃用户完成的“可验证健康改善周期”数量。** 一个周期至少包括：已确认基线、明确目标、干预记录、最低依从数据、到期复测和不确定性说明。它不是“健康一定改善”的承诺，而是“完整完成了可评价过程”。

以下为建议目标，不是当前现状；目标需在 30 天基线测量后校准。

| 层级 | 指标 | 90 天建议目标 | 注意事项 |
|---|---|---:|---|
| 激活 | 首次连接数据并完成首个有意义结果的用户比例 | ≥60% | 分设备、渠道和入口，不用页面浏览替代 |
| 主链路 | 五条核心旅程 E2E 通过率 | 100% | CI 通过不等于真实设备全部正常 |
| 留存 | 先锋场景 D30 留存 | ≥30%（探索目标） | 先测自然基线，避免为留存过度提醒 |
| 执行 | 计划完成率／复测完成率 | ≥60%／≥50% | 允许合理退出并记录原因 |
| 证据 | 活跃推荐真实证据或明确传统经验标注率 | 100% 状态可见 | 不等于全部升级为高等级临床证据 |
| 数据 | 未测量轴被误显示为确定分数的比例 | 0% | 缺失、冲突、低质量需独立状态 |
| 安全 | 预定义紧急高风险测试集召回率 | 100% 为目标并持续红队 | 不能据此声称现实零漏报 |
| Agent | 端到端任务成功率、工具正确率、无依据断言率 | 建立基线后逐版提升 | 按任务分档，拒答有时优于强答 |
| 性能 | 核心交互 P95 延迟／每完成周期模型成本 | 建立预算并逐版下降 | 成本按完成周期，不只按 token |
| 公平 | 关键人群／设备的失败率与校准差异 | 全量披露并设阈值 | 样本不足时明确不可判断 |
| 商业 | 付费周期完成率、机构续约、人工服务成本 | 由试点建立基线 | 防止收入依赖更多高风险建议 |

---

## 十一、工程验证实录与发布纪律

### 11.1 本次实际执行结果

- **前端构建：** `npm run build` 成功，Vite 5.4.21，144 个模块；主 JS 513.37 kB，gzip 159.12 kB，出现大于 500 kB 的 chunk 警告。建议按路由拆包，但优先级低于 P0。
- **主测试：** 初次全量 `pytest tests -q --tb=short` 在 300 秒达到审计时限，随后按目录和根级测试分组完成。
- **主测试合计：** **1,926 passed、19 failed、12 skipped。** 其中 `tests/api` 为 115 passed、2 skipped；`tests/core tests/lib` 为 1,317 passed、1 failed；`tests/tools tests/protocol tests/data` 为 261 passed、17 failed；根级 `tests/test_*.py` 为 233 passed、10 skipped、1 failed。
- **独立 Agent 测试：** `healthlens_agent/tests` 另为 **58 passed**。
- **失败解释：** 19 个失败集中在 Windows GBK 解码子进程输出、`stdout` 变为 `None` 的测试路径，指向跨平台测试可复现性问题；不能把它们写成算法失败，也不能忽略为“与发布无关”。
- **覆盖边界：** 本轮未形成 mypy、ruff 全量通过结论，也未执行所有重型可选依赖和真实外部设备／模型集成测试；因此不声称“全部测试通过”或“生产就绪”。
- **前端质量缺口：** 没有自动化测试脚本；`lint` 使用 ESLint，但 `package.json` 未声明 ESLint 依赖。[package](kimi-cite://md-line?path=C%3A%5CUsers%5Cxing%5CDesktop%5Chealthlens%5Cfrontend%5Cpackage.json&line=10&text=%22lint%22%3A%20%22eslint%20src%2F%20--fix%22 "citation")

### 11.2 每次发布必须具备的四道门

1. **契约门：** 数据库迁移、API schema、权限矩阵、前端契约与版本一致。
2. **任务门：** 五条核心 E2E、Agent gold set、OCR 字段集、GraphRAG 引用集全部达到阈值。
3. **安全门：** 紧急规则、越权、文件上传、敏感缓存、Claims 和区域驻留无回归。
4. **真实世界门：** 发布后监测失败、投诉、人工接管、数据漂移、人群差异、成本和回滚；模型或证据变更可追溯到受影响用户功能。

---

## 十二、主要风险与决策门槛

| 风险 | 早期信号 | 应对与停止条件 |
|---|---|---|
| 范围继续膨胀 | 新模块增长但激活／复测不升 | 未通过 P0 和先锋周期出口前，停止新增平级功能 |
| 医疗承诺超过证据 | 页面仍出现诊断、治疗、确定疗效 | Claims 门禁不过不得发布；高风险内容转专业审核 |
| 合成指标被误读 | 用 ICC、合成档案证明真实疗效 | 所有指标旁标数据类型、样本和适用边界 |
| Agent 自动执行错误 | 工具可越权写入或引用不可追溯 | 写入默认草稿＋确认；无法审计则不上线 |
| 敏感数据泄露 | localStorage／缓存／日志出现健康或基因数据 | 默认最小化、加密、过期和删除；重大风险先下线相关通道 |
| 真实试点无法完成 | 设备连接差、缺失高、复测低 | 先修复产品和数据质量，不用统计模型掩盖低完成率 |
| 重型模型没有增量价值 | 指标提升小、成本和失败率升高 | 保留手工特征或小模型，停止重型接入 |
| 商业化依赖过多人工 | 每周期解释和客服成本持续增加 | 优先改善结构化数据与模板；不能安全自动化则明确服务边界 |
| 合作方数据治理不清 | 租户、授权、撤回和区域责任模糊 | 合同、技术和审计三者未齐，不进入真实数据交换 |

---

## 十三、最终建议：用三次“证明”完成项目跃迁

### 第一次证明：证明产品能被普通用户顺利完成

不是展示 325 个端点，而是让新用户不被卡住地完成连接、理解、行动和复测。这是 0–30 天唯一最重要的结果。

### 第二次证明：证明差异化建议值得信任

不是让回答更像医生，而是使每条建议都有清晰的数据、规则、证据、适用边界和专家责任；不知道时能够明确说不知道。

### 第三次证明：证明长期数据能产生增量价值

不是积累更多历史记录，而是让个人基线、n-of-1 实验和复测真正改变下一次建议，并以真实世界指标证明比静态报告更有用。

**如果只能保留一句战略建议：HealthLens 应从“功能最丰富的中西医 AI 平台”，转向“最能把中西医融合健康建议做成可验证个人实验的平台”。** 前者容易被更大的模型和生态复制，后者能够由语义资产、治理、纵向数据和真实世界证据共同形成长期壁垒。

---

## 附录 A：建议立即创建的团队工作单

1. `P0-FE-01`：统一 Onboarding 答案键，补组件与 E2E。
2. `P0-FE-02`：接通 HealthAssess 提交，覆盖加载、失败和重试。
3. `P0-FE-03`：Agent SSE `finally` 清理、消息幂等、断流恢复。
4. `P0-AUTH-01`：统一 SSE／multipart 鉴权，补 401／refresh／重试矩阵。
5. `P0-AUTH-02`：重构 TOTP 第二因素挑战、限流、审计和恢复。
6. `P0-QA-01`：Windows UTF-8、Linux＋Windows CI、前端测试脚本与依赖。
7. `P1-SEC-01`：token、聊天、缓存、分享和日志的敏感数据流图与整改。
8. `P1-PROD-01`：Today＋四任务导航＋睡眠 8 周实验。
9. `P1-EVID-01`：活跃推荐证据反查和合成证据隔离。
10. `P1-RES-01`：30–60 人试点协议、同意、统计计划和退出规则。

## 附录 B：主要外部参考

- Stanford HAI，AI Index 2026 与医学章节：Agent 任务评价、医疗 AI 与专用模型趋势。[AI Index](kimi-cite://web?url=https%3A%2F%2Fhai.stanford.edu%2Fassets%2Ffiles%2Fai_index_report_2026.pdf "citation") [Medicine](kimi-cite://web?url=https%3A%2F%2Fhai.stanford.edu%2Fassets%2Ffiles%2Fai_index_report_2026_chapter_6_medicine.pdf "citation")
- WHO，医疗健康大模型伦理与治理。[WHO](kimi-cite://web?url=https%3A%2F%2Fwww.who.int%2Fnews%2Fitem%2F18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models "citation")
- FDA，AI 医疗器械与 PCCP。[FDA AI](kimi-cite://web?url=https%3A%2F%2Fwww.fda.gov%2Fmedical-devices%2Fdigital-health-center-excellence%2Fartificial-intelligence-enabled-medical-devices "citation") [PCCP](kimi-cite://web?url=https%3A%2F%2Fwww.fda.gov%2Fregulatory-information%2Fsearch-fda-guidance-documents%2Fmarketing-submission-recommendations-predetermined-change-control-plan-artificial-intelligence "citation")
- 欧盟委员会，AI Act 导航与最新官方材料。[AI Act FAQ](kimi-cite://web?url=https%3A%2F%2Fdigital-strategy.ec.europa.eu%2Fen%2Ffaqs%2Fnavigating-ai-act "citation")
- PaPaGei，生理信号基础模型。[ICLR](kimi-cite://web?url=https%3A%2F%2Ficlr.cc%2Fvirtual%2F2025%2Fposter%2F28573 "citation") [代码与模型资料](kimi-cite://web?url=https%3A%2F%2Fgithub.com%2Fnokia-bell-labs%2Fpapagei-foundation-model "citation")
- 数字孪生方法与验证讨论。[Nature Biomedical Engineering](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs41551-026-01733-4.pdf "citation") [Nature Reviews Methods Primers](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs43586-025-00454-3 "citation")
- 合成数据效用与隐私评价。[Scientific Reports](kimi-cite://web?url=https%3A%2F%2Fwww.nature.com%2Farticles%2Fs41598-024-72894-y "citation")
- 竞品公开资料：ChatGPT Health、Function Health、Superpower、Oura Advisor、Google Health Coach，正文相应段落已逐条引用。
