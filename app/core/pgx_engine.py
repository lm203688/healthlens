"""药物基因组学(PGx)引擎
Phase 1: 基于基因型→表型→用药建议的规则引擎
Phase 2: CPIC guidelines 完整实现 + AI 辅助

参考:
- CPIC (Clinical Pharmacogenetics Implementation Consortium)
- PharmGKB (Pharmacogenomics Knowledgebase)
- FDA Table of Pharmacogenomic Biomarkers
"""
from dataclasses import dataclass
from loguru import logger


@dataclass
class PGxResult:
    gene_symbol: str
    phenotype: str           # 代谢型: PM(差代谢) / IM(中间代谢) / NM(正常代谢) / RM(快速代谢) / UM(超快代谢)
    genotype: str            # *1/*1, *1/*2 等
    activity_score: float    # 活性评分 0-3
    drug_recommendations: list[dict]  # 药物建议列表


# 药物基因组学规则库
# key: 基因符号, value: 等位基因→活性评分映射
PGX_RULES = {
    "CYP2D6": {
        "alleles": {
            "*1": 1.0,   # 正常功能
            "*2": 1.0,   # 正常功能
            "*4": 0.0,   # 无功能
            "*5": 0.0,   # 基因缺失
            "*10": 0.5,  # 下降
            "*17": 0.5,  # 下降
            "*41": 0.5,  # 下降
        },
        "phenotype_map": {  # 活性评分→代谢倾向（wellness 措辞，非临床表型）
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.0): ("IM", "代谢倾向中偏慢"),
            (1.1, 2.25): ("NM", "代谢倾向常规"),
            (2.3, 3.0): ("UM", "代谢倾向偏快"),
        },
        "drugs": [
            {"name": "可待因(Codeine)", "class": "镇痛药"},
            {"name": "他莫昔芬(Tamoxifen)", "class": "抗肿瘤"},
            {"name": "阿米替林(Amitriptyline)", "class": "抗抑郁"},
            {"name": "美托洛尔(Metoprolol)", "class": "心血管"},
            {"name": "右美沙芬(Dextromethorphan)", "class": "镇咳"},
        ],
    },
    "CYP2C19": {
        "alleles": {
            "*1": 1.0,   # 正常
            "*2": 0.0,   # 无功能
            "*3": 0.0,   # 无功能
            "*4": 0.0,   # 无功能
            "*17": 1.5,  # 增强
        },
        "phenotype_map": {
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.99): ("IM", "代谢倾向中偏慢"),
            (2.0, 2.49): ("NM", "代谢倾向常规"),
            (2.5, 3.1): ("RM", "代谢倾向偏快"),
        },
        "drugs": [
            {"name": "氯吡格雷(Clopidogrel)", "class": "抗血小板"},
            {"name": "奥美拉唑(Omeprazole)", "class": "PPI"},
            {"name": "伏立康唑(Voriconazole)", "class": "抗真菌"},
            {"name": "西酞普兰(Citalopram)", "class": "抗抑郁"},
            {"name": "苯妥英(Phenytoin)", "class": "抗癫痫"},
        ],
    },
    "CYP2C9": {
        "alleles": {
            "*1": 1.0,
            "*2": 0.5,
            "*3": 0.0,
        },
        "phenotype_map": {
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.0): ("IM", "代谢倾向中偏慢"),
            (1.1, 2.0): ("NM", "代谢倾向常规"),
        },
        "drugs": [
            {"name": "华法林(Warfarin)", "class": "抗凝"},
            {"name": "苯妥英(Phenytoin)", "class": "抗癫痫"},
            {"name": "塞来昔布(Celecoxib)", "class": "NSAID"},
            {"name": "洛沙坦(Losartan)", "class": "降压"},
        ],
    },
    "VKORC1": {
        "alleles": {
            "GG": 1.0,
            "GA": 0.5,
            "AA": 0.0,
        },
        "phenotype_map": {
            (0, 0.4): ("高敏感性", "华法林高敏感性"),
            (0.5, 0.9): ("中等敏感性", "华法林中等敏感性"),
            (1.0, 1.5): ("正常敏感性", "华法林正常敏感性"),
        },
        "drugs": [
            {"name": "华法林(Warfarin)", "class": "抗凝"},
        ],
    },
    "DPYD": {
        "alleles": {
            "*1": 1.0,
            "*2A": 0.0,
            "*13": 0.0,
            "HapB3": 0.5,
        },
        "phenotype_map": {
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.0): ("IM", "代谢倾向中偏慢"),
            (1.1, 2.0): ("NM", "代谢倾向常规"),
        },
        "drugs": [
            {"name": "5-氟尿嘧啶(5-FU)", "class": "化疗"},
            {"name": "卡培他滨(Capecitabine)", "class": "化疗"},
            {"name": "替加氟(Tegafur)", "class": "化疗"},
        ],
    },
    "TPMT": {
        "alleles": {
            "*1": 1.0,
            "*2": 0.0,
            "*3A": 0.0,
            "*3B": 0.0,
            "*3C": 0.0,
        },
        "phenotype_map": {
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.0): ("IM", "代谢倾向中偏慢"),
            (1.1, 2.0): ("NM", "代谢倾向常规"),
        },
        "drugs": [
            {"name": "硫唑嘌呤(Azathioprine)", "class": "免疫抑制"},
            {"name": "6-巯基嘌呤(6-MP)", "class": "化疗"},
            {"name": "硫鸟嘌呤(6-TG)", "class": "化疗"},
        ],
    },
    "SLCO1B1": {
        "alleles": {
            "*1": 1.0,
            "*5": 0.0,
            "*15": 0.0,
            "*17": 0.5,
        },
        "phenotype_map": {
            (0, 0.5): ("低功能", "低转运功能"),
            (0.5, 0.9): ("中功能", "中等转运功能"),
            (1.0, 2.0): ("正常功能", "正常转运功能"),
        },
        "drugs": [
            {"name": "辛伐他汀(Simvastatin)", "class": "他汀类"},
            {"name": "阿托伐他汀(Atorvastatin)", "class": "他汀类"},
            {"name": "瑞舒伐他汀(Rosuvastatin)", "class": "他汀类"},
        ],
    },
    "UGT1A1": {
        "alleles": {
            "*1": 1.0,
            "*6": 0.0,
            "*28": 0.0,
            "*60": 0.5,
        },
        "phenotype_map": {
            (0, 0.5): ("PM", "代谢倾向偏慢"),
            (0.6, 1.0): ("IM", "代谢倾向中偏慢"),
            (1.1, 2.0): ("NM", "代谢倾向常规"),
        },
        "drugs": [
            {"name": "伊立替康(Irinotecan)", "class": "化疗"},
            {"name": "阿扎那韦(Atazanavir)", "class": "抗HIV"},
        ],
    },
}


# 基因-代谢倾向说明（去医疗化：仅作「代谢倾向提示」，不给出具体剂量指令）。
# 守住 wellness 边界：不诊断、不开方、不指定剂量；任何用药调整须由医师决定。
PGX_DISCLAIMER = (
    "基因-代谢倾向参考，非医学诊断、非用药处方。具体用药与剂量调整"
    "必须由持证医师结合完整临床情况决定。"
)

DRUG_ADVICE = {
    "PM": {
        "advice": "代谢偏慢倾向：常规剂量下该药物体内暴露可能偏高，建议与医师沟通个体化评估",
        "dose_adjustment": "是否调整剂量须由医师决定",
        "monitoring": "关注身体反应，必要时复诊",
    },
    "IM": {
        "advice": "代谢中等偏慢倾向：常规剂量可能略偏高，可与医师沟通",
        "dose_adjustment": "是否调整剂量须由医师决定",
        "monitoring": "常规关注疗效与耐受",
    },
    "NM": {
        "advice": "代谢倾向常规，无特殊提示",
        "dose_adjustment": "按标准方案即可",
        "monitoring": "常规即可",
    },
    "RM": {
        "advice": "代谢偏快倾向：常规剂量下暴露可能偏低、效果可能减弱，可与医师沟通",
        "dose_adjustment": "是否调整须由医师决定",
        "monitoring": "关注实际效果",
    },
    "UM": {
        "advice": "代谢偏快倾向：常规剂量下暴露可能明显偏低，建议与医师沟通",
        "dose_adjustment": "是否调整须由医师决定",
        "monitoring": "关注实际效果",
    },
}


class PGxEngine:
    """药物基因组学引擎"""

    def interpret_genotype(self, gene_symbol: str, genotype: str) -> PGxResult | None:
        """解析基因型，输出表型和用药建议"""
        gene_rule = PGX_RULES.get(gene_symbol)
        if not gene_rule:
            return None

        # 解析基因型 (如 "*1/*2", "GG", "GA")
        allele_scores = gene_rule["alleles"]
        parts = genotype.split("/")
        if len(parts) != 2 and gene_symbol != "VKORC1":
            # 非 VKORC1 的二倍体基因
            if genotype in allele_scores:
                # 单字母基因型
                score = allele_scores[genotype]
            else:
                return None
        else:
            # 二倍体
            if gene_symbol == "VKORC1":
                score = allele_scores.get(genotype, 1.0)
            else:
                score = 0
                for p in parts:
                    score += allele_scores.get(p.strip(), 1.0)

        # 确定表型：phenotype_map 的区间已改为「互不重叠」的显式边界
        # （对齐 CPIC：CYP2D6 AS 0.6–1.0 判 IM、1.1–3.0 判 NM；VKORC1 GA=0.5
        # 判中等敏感性）。因此每个活性评分只落进唯一区间，0.5 / 1.0 这类
        # 共享边界不再存在「同时命中两档」的歧义（P1 修复）。
        bands = [(low, high, ph, desc)
                 for (low, high), (ph, desc) in gene_rule["phenotype_map"].items()]
        matched = [b for b in bands if b[0] <= score <= b[1]]
        if len(matched) == 1:
            _, _, phenotype, phenotype_desc = matched[0]
        else:
            # 评分落在全部分档之外（未知等位基因组合）→ 就近归入边界最近的
            # 区间，而非静默降级成 NM，避免低活性基因型被误判为正常。
            _, _, phenotype, phenotype_desc = min(
                bands, key=lambda b: min(abs(score - b[0]), abs(score - b[1]))
            )

        # 生成药物建议
        drug_recs = []
        advice = DRUG_ADVICE.get(phenotype, DRUG_ADVICE["NM"])
        for drug in gene_rule["drugs"]:
            drug_recs.append({
                "drug_name": drug["name"],
                "drug_class": drug["class"],
                "advice": advice["advice"],
                "dose_adjustment": advice["dose_adjustment"],
                "monitoring": advice["monitoring"],
            })

        return PGxResult(
            gene_symbol=gene_symbol,
            phenotype=phenotype,
            genotype=genotype,
            activity_score=score,
            drug_recommendations=drug_recs,
        )

    async def analyze_user_genome(self, variants: list[dict]) -> list[dict]:
        """分析用户基因组数据，返回 PGx 解读结果"""
        results = []
        for variant in variants:
            gene = variant.get("gene_symbol") or variant.get("gene")
            genotype = variant.get("genotype")
            if not gene or not genotype:
                continue

            result = self.interpret_genotype(gene, genotype)
            if result:
                results.append({
                    "gene": result.gene_symbol,
                    "genotype": result.genotype,
                    "phenotype": result.phenotype,
                    "phenotype_note": "基因-代谢倾向参考（非诊断）",
                    "activity_score": result.activity_score,
                    "drug_count": len(result.drug_recommendations),
                    "top_drugs": [d["drug_name"] for d in result.drug_recommendations[:3]],
                    "disclaimer": PGX_DISCLAIMER,
                })

        logger.info(f"PGx analysis: {len(results)} genes interpreted from {len(variants)} variants")
        return results

    async def analyze_user_genome_enriched(self, variants: list[dict]) -> list[dict]:
        """在本地解读基础上叠加实时 CPIC 指南等级 (Phase 2)。

        离线/限流/导入失败时静默回退到本地规则, 不改变主流程语义。
        开关建议: 由调用方在 settings 中控制是否启用 (默认本地规则)。
        """
        results = await self.analyze_user_genome(variants)
        try:
            try:
                from app.core.clinpgx_client import enrich_gene_drugs
            except ImportError:
                from .clinpgx_client import enrich_gene_drugs  # type: ignore

            for r in results:
                gene = r.get("gene")
                genotype = r.get("genotype", "")
                base = self.interpret_genotype(gene, genotype)
                if not base:
                    continue
                enriched = await enrich_gene_drugs(gene, base.drug_recommendations)
                r["drug_recommendations"] = enriched
                r["drug_count"] = len(enriched)
                r["top_drugs"] = [d["drug_name"] for d in enriched[:3]]
                r["guidelines_attached"] = any(
                    "cpic_level" in d for d in enriched
                )
        except Exception as e:  # 离线/导入失败 → 保持本地结果
            logger.warning(f"PGx live guideline enrichment skipped: {e}")
        return results

    def get_drug_interactions(self, gene_results: list[dict]) -> list[dict]:
        """获取药物-基因代谢倾向交互摘要（wellness 措辞，非临床严重度）"""
        interactions = []
        for result in gene_results:
            gene = result.get("gene")
            genotype = result.get("genotype")
            if not gene or not genotype:
                continue

            pgx_result = self.interpret_genotype(gene, genotype)
            if pgx_result:
                for drug_rec in pgx_result.drug_recommendations:
                    if pgx_result.phenotype != "NM":  # 只报告非常规的
                        interactions.append({
                            "gene": gene,
                            "drug": drug_rec["drug_name"],
                            "drug_class": drug_rec["drug_class"],
                            "phenotype": pgx_result.phenotype,
                            "advice": drug_rec["advice"],
                            # wellness 措辞：不用 high/medium 临床严重度
                            "attention": "建议留意" if pgx_result.phenotype in ("PM", "UM") else "常规关注",
                            "disclaimer": PGX_DISCLAIMER,
                        })

        return interactions
