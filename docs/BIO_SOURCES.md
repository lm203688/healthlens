# 外部参考数据库接入（结构生物学 / 化学信息学 / 同源性检索）

> 版本：v0.34.0 起
> 代码：`app/connectors/reference/`、`app/api/bio.py`
> 测试：`tests/connectors/test_reference_sources.py`
> 实测日期：2026-11-01（全部端点均真实联网验证，非文档推演）

---

## 一、接入了什么

| 源 | 类型 | 需要 key | 主要能力 | 实测状态 |
|---|---|---|---|---|
| **RCSB PDB** | 实验结构档案 | 否 | 条目元数据、聚合物实体/链/物种、配体、全库检索 | ✅ 通 |
| **PubChem** | 化合物库（1 亿+） | 否 | 名称/SMILES/InChIKey→CID、计算属性、同义词/CAS、2D 相似性 | ✅ 通 |
| **NCBI BLAST** | 同源性比对 | 否（key 可加速） | blastn/blastp/blastx/tblastn/tblastx，JSON2 结构化结果 | ✅ 通 |
| **UniProt** | 蛋白元数据 | 否 | 条目查询、基因符号→登录号（枢纽） | ✅ 通 |
| **AlphaFold DB** | 预测结构 | 否 | 预测模型、pLDDT 分层、结构文件 URL | ✅ 通 |
| **Schrödinger** | 商业 CADD 套件 | **需自备许可** | PrepWizard/LigPrep/Epik/Glide/Prime MM-GBSA/Desmond/QikProp/SiteMap/WaterMap/FEP+ | ⚠️ 适配层就绪，未安装 |

**为什么多了 UniProt 和 AlphaFold**：RCSB 与 AlphaFold 都按 UniProt 登录号索引，不认基因名。没有 UniProt 这一环，"基因 → 结构"就断了。这两个是让前三个真正可用起来的必要补充，不是凑数。

---

## 二、API 一览（`/api/v1/bio`）

所有读接口**公开**（无用户数据，不需登录）；写接口（CADD 作业）需登录。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/sources` | 数据源能力矩阵；`?probe=true` 并发探活 |
| GET | `/pdb/{pdb_id}` | 条目完整描述（元数据 + 实体 + 配体，一次 GraphQL） |
| POST | `/pdb/search` | 全库检索（text / method / max_resolution / organism / released_after，AND 关系） |
| GET | `/pdb/by-uniprot/{accession}` | 按 UniProt 号列出已解析结构 |
| GET | `/compound?q=` | 化合物查询（自动识别名称 / SMILES / InChIKey） |
| GET | `/compound/{cid}` | 计算属性（分子式、MW、XLogP、TPSA、HBD/HBA…） |
| GET | `/compound/{cid}/synonyms` | 同义词 + CAS 号（含校验位验证） |
| POST | `/compound/similar` | 2D 指纹相似性（Tanimoto） |
| POST | `/blast` | 提交比对，立即返回 RID（**推荐**） |
| GET | `/blast/{rid}/status` | 任务状态 |
| GET | `/blast/{rid}/result` | 取结构化结果 |
| POST | `/blast/run` | 提交并同步等待（脚本用，默认 180s 超时） |
| GET | `/protein/gene/{symbol}` | 基因符号 → UniProt 登录号 |
| GET | `/protein/{accession}` | UniProt 条目元数据 |
| GET | `/structure/predicted/{accession}` | AlphaFold 预测结构（**非实验证据**） |
| GET | `/target/{gene_symbol}` | **靶点全景**：基因 → 蛋白 → 实验结构 + 预测结构 |
| GET | `/cadd/capabilities` | Schrödinger 安装/模块探测 |
| POST | `/cadd/jobs` | 执行 CADD 作业（需许可 + 登录） |

### 示例

```bash
# 血红蛋白结构
curl "http://localhost:8000/api/v1/bio/pdb/4HHB"

# 阿司匹林
curl "http://localhost:8000/api/v1/bio/compound?q=aspirin"

# 靶点全景（基因 → 结构）
curl "http://localhost:8000/api/v1/bio/target/TP53?max_structures=5"

# 找 3Å 以内的冷冻电镜结构
curl -X POST "http://localhost:8000/api/v1/bio/pdb/search" \
  -H "Content-Type: application/json" \
  -d '{"method":"ELECTRON MICROSCOPY","max_resolution":3.0,"limit":10}'

# 提交比对
curl -X POST "http://localhost:8000/api/v1/bio/blast" \
  -H "Content-Type: application/json" \
  -d '{"sequence":"ATGGATGATGATATCGCCGCGCTCGTCGTCGACAAC","program":"blastn","database":"core_nt"}'
```

---

## 三、四个必须知道的实现坑（都已踩过并绕过）

这些是"文档里不会写、但会让集成静默失效"的地方。改代码前务必先读。

### 1. BLAST 的 JSON2 是 **ZIP 包**，不是 JSON

`FORMAT_TYPE=JSON2` 返回的字节流以 `PK` 开头。直接 `json.loads` 必然失败。

包内结构：
```
<RID>.json       → {"BlastJSON": [{"File": "<RID>_1.json"}]}   ← 索引
<RID>_1.json     → {"BlastOutput2": {"report": {...}}}          ← 真正的报告
```

正确做法：先解 ZIP，读索引，按 `File` 指针跳转，再剥掉 `report` 外层。
`blast.py::fetch()` 已实现，测试 `test_blast_fetch_unwraps_zip` 锁死。

### 2. PubChem 相似性搜索不能带 `/cids/`

写成 `.../similarity/smiles/{s}/cids/JSON` 会得到
`PUGREST.BadRequest: Search input may not be combined with any operation`。

正确姿势：
```
GET  .../compound/similarity/smiles/{urlencode(smiles)}/JSON?Threshold=95
     → 202 {"Waiting": {"ListKey": "..."}}
GET  .../compound/listkey/{ListKey}/cids/JSON
     → 200 {"IdentifierList": {"CID": [...]}}
```
SMILES 必须整体 URL 编码（括号、等号都要编），否则路径被截断。

### 3. BLAST 公共队列可能排队**数小时**

同一时刻实测：
- `blastn` + `core_nt` → RTOE ≈ 30 秒
- `blastp` + `swissprot` → RTOE ≈ **34,781 秒**（约 9.7 小时）

所以接口**必须**拆成 submit / status / result 三步。`/blast/run` 只是脚本便利封装，
Web 主流程不要用——会把请求挂死。

批量或离线比对请用本地 BLAST+ 命令行。

### 4. RCSB GraphQL 字段名要实测，不能凭记忆

写错的字段（如 `polymer_entity_count_nonpolymer`）会让**整个查询**失败，
而不是只少一个字段。改查询前先跑一次真实请求验证。

---

## 四、速率、缓存与合规

| 源 | 限速实现 | 缓存 TTL |
|---|---|---|
| RCSB | 不限速（未公布硬限额） | 条目 24h / 检索 10min |
| PubChem | 0.21s/次（≈5 req/s，官方建议） | 7 天 |
| NCBI BLAST | 0.34s/次（3 req/s）；配 `NCBI_API_KEY` 后 0.11s | 不缓存（RID 即句柄） |
| UniProt | 0.12s/次 | 7 天 |
| AlphaFold | 0.12s/次 | 7 天 |

**必须遵守的上游政策**
- NCBI 要求带 `TOOL` + `EMAIL`，缺失会被降级排队。已在 `settings` 中暴露。
- 所有请求带自定义 User-Agent。
- 缓存只缓存成功结果，错误永不缓存（避免把瞬时故障固化）。

---

## 五、诚实边界（写进代码，不是写在文档里）

这一节比上面所有内容都重要——它决定这些数据能不能被信任。

| 边界 | 实现 |
|---|---|
| **AlphaFold 是预测，不是实验** | 返回体固定带 `evidence_type: "predicted"` 与 `disclaimer`；`target.py` 的 `evidence_policy` 明写"不得计入 L1/L2 证据等级" |
| **PubChem 属性是计算值** | 每个属性返回体带 `property_note: "均为 PubChem 计算属性（computed），非实验测定值"` |
| **Schrödinger 无许可必须报错** | `run_job()` 在未安装/模块缺失时抛 `license_unavailable`；**绝不返回 0 分或空结果**。测试 `test_schrodinger_run_job_raises_license_unavailable` 锁死 |
| **查无此项 ≠ 空结果** | 抛 `not_found`（HTTP 404），不返回 `{}` 冒充成功 |
| **上游故障不降级为假数据** | 抛 `upstream_error` / `timeout`（HTTP 502/504），由调用方决定重试或提示 |

错误码是前后端契约，改名会破坏调用方：

```
not_found / invalid_input / rate_limited / timeout /
network_error / upstream_error / parse_error /
license_unavailable / not_implemented
```

---

## 六、它对本项目意味着什么

### 1. 靶点链：从"一句结论"下沉到"已发表结构"

```
八轴弱项 / 证据卡里的靶点
    ↓ UniProt          P04637 (p53, 393 aa)
    ↓ RCSB PDB         323 个实验结构，可按分辨率/方法筛选
    ↓ AlphaFold        AF-P04637-F8-F1, pLDDT 83.6 (confident)
```

这是审稿人和 B 端客户都会问的那一层：**"你说这个通路重要，有什么结构证据？"**
以前只能回答"文献里有"，现在可以给出具体 PDB ID、分辨率、配体。

### 2. 化合物链：PGx 与食疗的化学底座

- 药物基因组学（`/genome/pgx`）输出"某基因型影响某药代谢"后，可直接接
  `/compound?q=<药名>` 拿到分子式、MW、XLogP、TPSA，以及相似化合物。
- 中药成分研究：`/compound/similar` 可在 1 亿化合物里找结构类似物，
  这是"某古籍方剂中的成分是否有现代药理对应物"的可计算入口。

### 3. CADD：为将来的分子工作留好接口

`/cadd/capabilities` 现在诚实返回 `installed: false`。一旦装上套件并配置
`SCHRODINGER`，同一套接口即可跑对接、MM-GBSA、FEP+，无需改代码。

---

## 七、怎么验证

```bash
# 离线契约测试（CI 默认）
pytest tests/connectors -q

# 含真实联网
HL_LIVE_BIO=1 pytest tests/connectors -q

# 手工探活全部数据源
curl "http://localhost:8000/api/v1/bio/sources?probe=true"
```

`/sources?probe=true` 会返回每个源的 `ok` / `latency_ms` / `error`，
部署后第一件事就该打这个接口。

---

## 八、已知限制与后续

| 限制 | 说明 | 后续 |
|---|---|---|
| BLAST 结果不落库 | 目前 RID 由调用方保存，进程重启即丢 | 可加 `blast_jobs` 表做异步任务与结果缓存 |
| 无批量接口 | 一次一个 PDB / 一个化合物 | 需要时加 `/pdb/batch`（注意上游限速） |
| Schrödinger 未验证真实作业 | 无许可环境只能验证探测与报错路径 | 有许可后跑一次 PrepWizard + Glide 冒烟 |
| PDB 结构摘要未解析 | 只给 ID + 元数据，不解析坐标 | 需要结合位点分析时再接 `struct_conn` / `pdbx_entity_instance` |

---

## 九、MCP 工具（Agent 通道，v0.39.0）

REST 是给前端和脚本用的；**Agent 走的是 MCP**。v0.38.0 只做了 REST，Agent
够不到这些数据——本轮把同一批能力注册成 8 个 MCP 工具，默认开启（公开只读库、
不含个人数据，因此不依赖 `HL_MCP_EXPOSE_PRIVATE`）。

| 工具 | 作用 | 典型问法 |
|---|---|---|
| `hl_target_profile` | 基因 → 蛋白 → 实验结构清单 → AlphaFold 模型（组合工具） | "TP53 有哪些结构证据？" |
| `hl_pdb_entry` | 单个 PDB 条目全貌（方法/分辨率/链/配体） | "4HHB 是什么结构？" |
| `hl_pdb_search` | RCSB 全库检索（条件 AND） | "2 Å 以内的人源激酶结构" |
| `hl_compound_lookup` | 名称/SMILES/InChIKey → CID + 属性 + CAS | "阿司匹林的分子量和 CAS 号" |
| `hl_compound_similar` | 2D 指纹相似性搜索 | "找和它骨架相似的化合物" |
| `hl_blast_submit` | 提交比对，返回 RID + 预估排队秒数 | "这条序列和已知蛋白同源吗" |
| `hl_blast_status` | 轮询任务状态 | — |
| `hl_blast_result` | 取解析后的命中与 HSP | — |

**BLAST 为什么拆三步**：NCBI 公共队列排队不可控，实测同一时刻 blastn 约 30 秒、
blastp+swissprot 曾达 34,781 秒（9.7 小时）。同步等待必然超时，所以提交与取结果
必须分开，工具描述里也明确要求轮询。

**调用示例**（MCP JSON-RPC）：

```bash
curl -s http://localhost:8000/api/v1/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"hl_pdb_entry","arguments":{"pdb_id":"4HHB"}}}'
```

**参数类型**：`inputSchema` 按真实类型声明（`integer` / `number` / `string`），
不再一律 `string`；handler 侧仍有 `_as_int` 兜底，兼容不严格遵守 schema 的客户端。

**同步/异步桥**：MCP handler 是同步函数、连接器是 async。若在 FastAPI 的 async
上下文里直接 `asyncio.run()` 会抛 `RuntimeError`，`_run_ref()` 检测到运行中的
事件循环时退化到独立线程新建循环。

