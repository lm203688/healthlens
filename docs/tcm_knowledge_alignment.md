# TCM-MKG 知识层对齐报告（二期交付物）

> 生成日期：2026-09-09｜对应研发路线：Section 一 P1 / P1 续 / P1-2
> 目的：记录 GraphAI-for-TCM（TCM-MKG）饮片实体与 HealthLens 既有 613 实体库、
> `tcm_pathway_map.json`、`tcm_formula_engine`、`tcm_safety` 的对齐方式与诚实边界。

---

## 一、数据来源与入库规模

| 项 | 内容 |
|---|---|
| 上游项目 | GraphAI-for-TCM（github.com/ZENGJingqi/GraphAI-for-TCM，MIT）+ Zenodo DOI 10.5281/zenodo.13763953 |
| 入库工具 | `tools/ingest_tcm_mkg.py`（幂等、确定性、字节级可复现） |
| 产出文件 | `data/tcm_mkg/chp_entities.json` |
| 饮片实体数 | **6,207 条**（名称/同义词/拼音/英文/来源库/药性五味/证据等级/完整溯源） |
| 药性关联率 | 100%（每条均带药性关联字段） |
| 实体库总规模 | 613（古籍结构化）→ **6,820 条** |

> 网络边界实录：raw.githubusercontent 本机时通时断、Zenodo API 限流，全量 1.1GB TSV
> 不落地；仅蒸馏饮片主表 + 药性表两个小文件入库。`CHP_Encoder.tsv`（6.5MB 分子指纹）
> 暂缓入库（属机制假说层，非当前安全推理必需）。

---

## 二、与既有模块的对接点

### 2.1 `app/core/tcm_formula_engine.py`（性味归经查询 + 配伍推理）
- CHP 6,207 饮片并入药材库（`_get_herb_database()`，实测 db=6,208，策展 15 味优先去重）。
- 英文药性映射：`Warm therapeutic → 温`、`Sweet medicinal → 甘`、`Lung meridian → Lung` 等。
- `get_herb_info()` 支持 CHP 别名归一 + 模糊匹配（实测「阿尔泰多榔菊」性=温、归肺经）。
- `check_compatibility(herb_names, medications, foods)` 委托 `tcm_safety.check_safety`
  做配伍 + 中西药 + 药-草-食三联推理。

### 2.2 `app/core/tcm_safety.py`（确定性安全护栏）
- 十八反（17 对）/ 十九畏（9 对）/ 妊娠禁忌（禁用+慎用）/ 中西药相互作用（8 类）。
- `HERB_SYNONYMS` 别名归一：42 经典 → CHP 广度增强至 **87 条**（防御式，仅并入命中
  经典 canonical 的别名，绝不改变既有语义）。
- **P1-2 新增**：药-草-食三联相互作用（`FOOD_DRUG_INTERACTIONS` / `FOOD_HERB_INTERACTIONS`
  / `FOOD_SYNONYMS` / `classify_food`），覆盖葡萄柚×抗凝药、牛奶×四环素、萝卜×人参等。

### 2.3 别名与实体一致性
- 别名索引 `_CHP_SYN` 的 value 必为 `_CHP_INDEX` 中存在的 canonical（单测 `test_syn_index_consistency` 强制）。

---

## 三、诚实边界声明（不可省略）

1. **机制假说，非临床结论**：CHP 药性/归经/草-分子关系多为文献挖掘，非 RCT 验证；
   任何机制解释输出必须标注「机制假说，非临床结论」。
2. **不伪造组学数据**：未接入 DNAm / 代谢组原始数据；相关量化（如代谢-炎症轴）为透明
   体检指标代理，硬标注 `not_clinical=True`。
3. **去医疗化合规**：所有安全校验仅做「风险提示 + 就医建议」，不删除原方案、不开方、
   不诊断（见 `tcm_safety` / `safety.py` 双闸门）。
4. **药-草-食传统理论分级**：食物×中药交互多属传统理论，等级标注 `low` 并注「传统理论，非临床结论」。

---

## 四、已知缺口与后续

| 缺口 | 状态 | 处置 |
|---|---|---|
| `CHP_Encoder.tsv` 分子指纹未入库 | 暂缓 | 仅影响机制可视化，非安全推理必需 |
| 食物×中药交互偏少（仅 4 组传统） | 已落地框架 | 后续可借 HerbKG 本体扩充「草-分子-靶点」机制解释 |
| `risk_engine` 直接消费药-草-食交互 | 未接 | 当前经 `tcm_safety` 统一入口分发，风险评分层保持循证指南独立 |

---

## 五、验证

- 离线 harness（stub 包注册 + loguru stub，绕过 `app/__init__` fastapi 链）：**P1-2 + P2-2 共 15 项断言全过**。
- 单测（标准 pytest，随代码入库）：`test_tcm_safety.py`（16 项，含 6 项食物交互）、
  `test_tcm_formula_engine_chp.py`（9 项，含 2 项食物路径）、`test_safety_triage.py`（5 项分诊）。
