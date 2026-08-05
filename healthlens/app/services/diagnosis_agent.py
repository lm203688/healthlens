"""核心诊断 AI 引擎 - 五层因果链融合诊断"""
import json
from typing import Any

from loguru import logger

from app.services.bio_database import (
    fetch_clinvar,
    fetch_kegg_pathway,
    fetch_string_network,
    fetch_uniprot,
)


# ---------------------------------------------------------------------------
# Demo 数据回退
# ---------------------------------------------------------------------------

def getFusionDemoData() -> dict:
    """从现有 fusion.py 的 DEMO_FUSION_CHAIN 获取回退数据"""
    from app.api.fusion import DEMO_FUSION_CHAIN
    return DEMO_FUSION_CHAIN


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一位融合中西医的**首席精准健康分析师**，负责把零散的健康数据（基因变异、蛋白功能、细胞通路、检验指标、中医症状）整合为一份**有深度、可判断、可执行**的因果链健康分析报告。

## 核心定位
你输出的不是医疗诊断或处方，而是**精准健康养生方案**——像一位既懂分子机制、又懂中医体质、还懂循证营养的私人健康顾问。当用户数据不足以支撑结论时，你敢于说"证据不足"，而不是编造。

## 五层因果链模型
- **L1 基因变异层**：基因符号、rsID、HGVS、临床意义（ClinVar）、等位基因频率。
- **L2 蛋白功能层**：L1 基因编码蛋白的分子功能、信号通路参与、结构/功能影响。
- **L3 细胞通路层**：受 L2 异常影响的信号通路及其激活/抑制状态、评分、严重程度。
- **L4 中医证候层**：从 L1-L3 客观数据反推中医证候（而非望闻问切），建立"分子机制→证候"的桥接。
- **L5 干预方案层**：针对 L4 的药食同源/频率修复/日常修复方案，体现"加法思维"（建议**添加什么**）。

## 你的三大核心能力要求（这是报告质量的底线）

### 一、综合性判断（Comprehensive Judgment）
不要孤立地罗列各层，而要**交叉验证、全局综合**：
1. **跨层对账**：把基因层(L1/L2/L3)、检验指标(lab_results)、中医症状(tcm_symptoms)三方放在一起看，找出彼此印证或相互矛盾之处。
2. **主导因果链(Dominant Chain)**：从所有异常中识别出 1-3 条最关键的因果主线（例如 "APOE ε4 → 脂质代谢通路抑制 → 中医'痰湿/肾虚'倾向 → 认知与心血管风险"），作为报告主轴。
3. **矛盾与缺口(Contradictions & Gaps)**：明确写出"哪些数据相互矛盾""哪些关键数据缺失导致判断受限"，并说明缺失数据会怎样改变结论。
4. **统一健康画像**：用一句话概括用户的整体体质/风险画像，避免各层结论互相打架。

### 二、深度分析（Deep Analysis）
每一处结论都要有**深度**而非套话：
1. **证据强度(Evidence Level)**：每条关键结论标注证据等级——`high`(多源/已知通路/权威数据库)、`medium`(单源/推断合理)、`low`(弱关联/猜测)。明确区分"已知事实"与"合理推测"。
2. **置信度(Confidence)**：对 L4 证候、L5 方案给出 0-1 的 confidence，并说明置信来源。
3. **风险分层(Risk Stratification)**：结合检验指标与年龄/性别线索，对心血管、代谢、认知等维度做风险分级（low/moderate/high/very_high），说明严重程度与紧迫度。
4. **机制深度**：解释"为什么"（分子/通路层面的因果机理），而不只是"是什么"。
5. **不确定性管理**：数据不足时合理推断并显式标注不确定性，不夸大、不隐瞒。

### 三、报告建议（Actionable Recommendations）
建议必须**可排序、可执行、有时间感**：
1. **优先级动作(Priority Actions)**：输出 P0(立即/高风险)、P1(近期重点)、P2(长期养护) 三级清单，每条含：做什么、为什么(机制/证据)、怎么做(具体)、时机(timing)、难度(effort)。
2. **加法思维**：食养方案建议"可以加入/不妨试试"，而非禁止；给出具体食材、用量、简单做法。
3. **闭环路径**：明确"下一步该补什么数据 / 何时复查 / 什么信号要就医"，让用户知道如何推进。
4. **语气**：亲切但不轻浮，用"方案/配方/分析/修复/建议"等健康管理语言；禁用"处方/治疗/诊断"等医疗用语。

## 输出要求
- 必须以 JSON 格式输出，结构见用户提示词。L1/L2 直接复用输入字段（不遗漏），L3 更新状态与评分，L4/L5 由你生成。
- 在 `summary` 内必须包含 `comprehensive_assessment`(综合判断, 2-4 句)、`dominant_chain`(主导因果链文本)、`data_gaps`(数据缺口)、`contradictions`(矛盾点)。
- 在 `layers` 外层附加 `priority_actions`(P0/P1/P2)、`risk_stratification`(各维度风险级)、`evidence_summary`(整体证据概览)。
- 每条 L4 证候与 L5 方案都要带 `confidence` 与 `evidence_level`。
- 中医桥接(tcm_bridge)须有"分子机制→证候"的逻辑推演。
- 如果数据严重不足，仍要输出结构化结果，但在 `summary.data_gaps` 与 `evidence_summary` 中诚实说明。
"""


# ---------------------------------------------------------------------------
# Agent 类
# ---------------------------------------------------------------------------

class DiagnosisAgent:
    """
    融合诊断 Agent - 将基因变异、蛋白功能、细胞通路、中医证候和干预方案
    整合为五层因果链诊断报告。
    """

    async def run_full_diagnosis(self, user_data: dict) -> dict:
        """
        运行完整诊断流程。

        Args:
            user_data: 用户数据字典，包含:
                - genes: 基因变异列表 [{gene_symbol, rsid, hgvs, uniprot_id?, ...}]
                - lab_results: 检验指标列表 [{name, value, unit, reference_range, ...}]
                - tcm_symptoms: 中医症状列表 ["气短乏力", "腰膝酸软", ...]
                - user_id: 用户 ID (可选)

        Returns:
            与 getFusionDemoData 格式兼容的五层因果链字典
        """
        genes = user_data.get("genes", [])
        lab_results = user_data.get("lab_results", [])
        tcm_symptoms = user_data.get("tcm_symptoms", [])
        user_id = user_data.get("user_id", "unknown")

        logger.info(f"开始 AI 诊断 | user_id={user_id} | variants={len(genes)} | labs={len(lab_results)} | symptoms={len(tcm_symptoms)}")

        # ---- Step 1: L1 基因变异注释 (ClinVar) ----
        layer1_variants = await self._annotate_variants(genes)

        # ---- Step 2: L2 蛋白功能注释 (UniProt) ----
        layer2_proteins = await self._annotate_proteins(genes)

        # ---- Step 3: L3 细胞通路注释 (KEGG) ----
        layer3_pathways = await self._annotate_pathways(layer2_proteins)

        # ---- Step 4: 构建 L1-L5 结构化数据 ----
        structured_data = self._build_structured_data(
            layer1_variants=layer1_variants,
            layer2_proteins=layer2_proteins,
            layer3_pathways=layer3_pathways,
            lab_results=lab_results,
            tcm_symptoms=tcm_symptoms,
        )

        # ---- Step 5: 调用 LLM 生成诊断报告 ----
        try:
            fusion_chain = await self._call_llm_for_diagnosis(structured_data)
            logger.info(f"AI 诊断完成 | user_id={user_id}")
            return fusion_chain
        except Exception as exc:
            logger.error(f"LLM 调用失败，回退到 Demo 数据 | error={exc}")
            return getFusionDemoData()

    # ------------------------------------------------------------------
    # L1: ClinVar 变异注释
    # ------------------------------------------------------------------

    async def _annotate_variants(self, genes: list[dict]) -> list[dict]:
        """使用 ClinVar 注释每个基因变异的临床意义"""
        variants = []
        for gene in genes:
            rsid = gene.get("rsid", "")
            hgvs = gene.get("hgvs", "")
            gene_symbol = gene.get("gene_symbol", "")

            clinvar_data = None
            query = rsid or hgvs
            if query:
                clinvar_data = await fetch_clinvar(query)

            variant_entry = {
                "gene_symbol": gene_symbol,
                "rsid": rsid,
                "hgvs": hgvs,
                "clinical_significance": clinvar_data.get("clinical_significance", "Unknown") if clinvar_data else "Unknown",
                "description": clinvar_data.get("title", "") if clinvar_data else f"{gene_symbol} 变异（{rsid or hgvs}）",
                "allele_frequency": gene.get("allele_frequency", 0),
                "source": "ClinVar" if clinvar_data else "UserInput",
            }
            variants.append(variant_entry)

        return variants

    # ------------------------------------------------------------------
    # L2: UniProt 蛋白功能注释
    # ------------------------------------------------------------------

    async def _annotate_proteins(self, genes: list[dict]) -> list[dict]:
        """使用 UniProt 注释蛋白功能"""
        proteins = []
        seen_genes: set[str] = set()

        for gene in genes:
            gene_symbol = gene.get("gene_symbol", "")
            uniprot_id = gene.get("uniprot_id", "")

            if gene_symbol in seen_genes:
                continue
            seen_genes.add(gene_symbol)

            uniprot_data = None
            if uniprot_id:
                uniprot_data = await fetch_uniprot(uniprot_id)

            protein_entry = {
                "gene_symbol": gene_symbol,
                "uniprot_id": uniprot_id or (uniprot_data.get("uniprot_id", "") if uniprot_data else ""),
                "protein_name": uniprot_data.get("protein_name", "") if uniprot_data else f"{gene_symbol} protein",
                "function": uniprot_data.get("function", "") if uniprot_data else "功能未知",
                "pathways": uniprot_data.get("pathways", []) if uniprot_data else [],
                "structure_source": "UniProt",
                "pdb_id": None,
                "interaction_partners": [],
                "variant_impact": gene.get("variant_impact", "待分析"),
            }
            proteins.append(protein_entry)

        return proteins

    # ------------------------------------------------------------------
    # L3: KEGG 通路注释
    # ------------------------------------------------------------------

    async def _annotate_pathways(self, proteins: list[dict]) -> list[dict]:
        """使用 KEGG 注释涉及的信号通路"""
        pathways = []
        seen_pw: set[str] = set()

        for protein in proteins:
            for pw_id in protein.get("pathways", []):
                if pw_id in seen_pw:
                    continue
                seen_pw.add(pw_id)

                kegg_data = await fetch_kegg_pathway(pw_id)
                pathway_entry = {
                    "pathway_id": pw_id,
                    "name": kegg_data.get("name", pw_id) if kegg_data else pw_id,
                    "display_name": kegg_data.get("name", pw_id) if kegg_data else pw_id,
                    "description": kegg_data.get("description", "") if kegg_data else "",
                    "category": "Unknown",
                    "status": "unknown",
                    "score": 50,
                    "severity": "待评估",
                    "related_genes": kegg_data.get("genes", []) if kegg_data else [protein["gene_symbol"]],
                    "tcm_bridge": "待 AI 分析映射",
                }
                pathways.append(pathway_entry)

        # 如果没有任何通路数据，生成默认占位
        if not pathways:
            for protein in proteins:
                pathways.append({
                    "pathway_id": f"custom_{protein['gene_symbol'].lower()}",
                    "name": f"{protein['gene_symbol']} related pathway",
                    "display_name": f"{protein['gene_symbol']} 相关通路",
                    "description": protein.get("function", ""),
                    "category": "Unknown",
                    "status": "unknown",
                    "score": 50,
                    "severity": "待评估",
                    "related_genes": [protein["gene_symbol"]],
                    "tcm_bridge": "待 AI 分析映射",
                })

        return pathways

    # ------------------------------------------------------------------
    # 构建结构化数据
    # ------------------------------------------------------------------

    def _build_structured_data(
        self,
        layer1_variants: list[dict],
        layer2_proteins: list[dict],
        layer3_pathways: list[dict],
        lab_results: list[dict],
        tcm_symptoms: list[str],
    ) -> dict:
        """构建注入 LLM 的结构化数据"""
        return {
            "layer1_variants": layer1_variants,
            "layer2_proteins": layer2_proteins,
            "layer3_pathways": layer3_pathways,
            "lab_results": lab_results,
            "tcm_symptoms": tcm_symptoms,
            "layer4_target_count": max(1, min(5, len(layer3_pathways))),
            "layer5_target_count": max(1, min(8, len(layer3_pathways) * 2)),
        }

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    async def _call_llm_for_diagnosis(self, structured_data: dict) -> dict:
        """
        调用 Agnes AI LLM 生成诊断报告。

        Returns:
            解析为 dict 的五层因果链，与 getFusionDemoData 格式兼容
        """
        from app.services.agnes_ai import call_llm

        user_prompt = self._build_user_prompt(structured_data)
        llm_response = await call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="agnes-v1",
            temperature=0.3,
        )

        # 解析 LLM 返回的 JSON
        return self._parse_llm_response(llm_response)

    def _build_user_prompt(self, data: dict) -> str:
        """构建注入给 LLM 的用户提示词"""
        data_json = json.dumps(data, ensure_ascii=False, indent=2)

        return f"""请根据以下结构化健康数据，生成一份**有深度、可综合判断、可执行**的五层因果链健康分析报告。

## 输入数据

```json
{data_json}
```

## 任务（严格按下列顺序与要求）

### A. 综合性判断（先做全局对账，再分层）
1. 把 L1/L2/L3（基因·蛋白·通路）、`lab_results`（检验指标）、`tcm_symptoms`（中医症状）三方交叉对照，找出相互印证与矛盾之处。
2. 提炼 **1-3 条主导因果链(dominant_chain)**：从所有异常中识别最关键主线，作为报告主轴。
3. 列出 **数据缺口(data_gaps)** 与 **矛盾点(contradictions)**，并说明它们如何影响结论可靠性。

### B. 分层生成
1. **L4 中医证候层**：依据 `tcm_symptoms` 与 L3 通路异常推导 L4 证候。
   - 每条含: name, description, related_pathways, score(0-100), **confidence(0-1)**, modern_interpretation, key_evidence, **evidence_level(high/medium/low)**
   - 关键：建立 `tcm_bridge` —— 从分子机制到证候的逻辑桥梁，并标注置信度。
2. **L5 干预方案层**：针对每个证候生成个性化干预。
   - intervention_type: food_medicine(药食同源) / targeted_drug / gene_therapy / pharmacogenomic
   - 每条含: name, description, target_pathways, target_syndromes, mechanism, **evidence_level**, **confidence**, active_compounds, timing(适合时机), effort(难度:极低/低/中)
   - 体现"加法思维"：用"可以试试/不妨加入"语气，给出具体食材、用量、简单做法。
3. **更新 L3**：依变异与蛋白功能异常，重评 L3 通路 status(upregulated/downregulated/normal/slightly_downregulated)与 score。

### C. 综合输出（顶层）
- **priority_actions**：P0(立即/高风险)/P1(近期重点)/P2(长期养护) 三级动作清单，每条含 action/why(机制或证据)/how(具体)/timing/effort。
- **risk_stratification**：对 心血管/代谢/认知/免疫 等维度做风险分级(low/moderate/high/very_high)并简述依据。
- **evidence_summary**：整体证据强度概览（数据是否充足、主要不确定来源）。

### D. summary
- 必含: total_variants, pathogenic_count, benign_count, likely_pathogenic_count, pathway_abnormal_count, dominant_syndrome, repair_chain_summary,
  **comprehensive_assessment**(综合判断 2-4 句), **dominant_chain**(主导因果链文本), **data_gaps**(数据缺口列表), **contradictions**(矛盾点列表), evidence_note。

## 输出格式

请输出完整 JSON（严格遵守结构，顶层可超出下列字段以容纳 C 项）：
```json
{{
  "user_id": "user",
  "layers": {{
    "layer1_variants": [...],
    "layer2_proteins": [...],
    "layer3_pathways": [...],
    "layer4_syndromes": [...],
    "layer5_interventions": [...]
  }},
  "priority_actions": {{
    "P0": [{{"action":"","why":"","how":"","timing":"","effort":""}}],
    "P1": [...],
    "P2": [...]
  }},
  "risk_stratification": [
    {{"dimension":"心血管","level":"moderate","basis":""}},
    {{"dimension":"代谢","level":"low","basis":""}},
    {{"dimension":"认知","level":"","basis":""}},
    {{"dimension":"免疫","level":"","basis":""}}
  ],
  "evidence_summary": {{"data_adequacy":"","main_uncertainty":""}},
  "summary": {{
    "total_variants": ...,
    "pathogenic_count": ...,
    "benign_count": ...,
    "likely_pathogenic_count": ...,
    "pathway_abnormal_count": ...,
    "dominant_syndrome": "...",
    "repair_chain_summary": "...",
    "comprehensive_assessment": "...",
    "dominant_chain": "...",
    "data_gaps": ["..."],
    "contradictions": ["..."],
    "evidence_note": "..."
  }}
}}
```

注意：L1 和 L2 直接复用输入内容（不遗漏任何字段）；L3 更新状态与评分；L4/L5 由你生成并带 confidence 与 evidence_level。
只输出 JSON，不要附加其他文字。"""

    def _parse_llm_response(self, response: str) -> dict:
        """解析 LLM 返回的文本为五层因果链字典"""
        # 尝试提取 JSON 块
        text = response.strip()

        # 移除 markdown 代码块标记
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM 返回的 JSON 解析失败，尝试提取 JSON 块")
            # 尝试查找第一个 { 到最后一个 }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    logger.error("JSON 提取仍然失败，回退到 Demo 数据")
                    return getFusionDemoData()
            else:
                return getFusionDemoData()

        # 验证结构完整性
        if "layers" not in data:
            logger.warning("LLM 返回数据缺少 layers 字段，回退到 Demo")
            return getFusionDemoData()

        # 确保五层都存在
        expected_layers = {
            "layer1_variants", "layer2_proteins", "layer3_pathways",
            "layer4_syndromes", "layer5_interventions",
        }
        for layer_name in expected_layers:
            if layer_name not in data.get("layers", {}):
                data.setdefault("layers", {})[layer_name] = []

        if "summary" not in data:
            data["summary"] = {}

        # 确保综合判断/深度分析相关的顶层字段存在（前端与下游兼容）
        data.setdefault("priority_actions", {"P0": [], "P1": [], "P2": []})
        data.setdefault("risk_stratification", [])
        data.setdefault("evidence_summary", {"data_adequacy": "未知", "main_uncertainty": ""})

        # summary 内补全综合判断字段
        summary = data.setdefault("summary", {})
        for key in ("comprehensive_assessment", "dominant_chain", "data_gaps", "contradictions"):
            summary.setdefault(key, "" if key not in ("data_gaps", "contradictions") else [])

        return data