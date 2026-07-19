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
        "phenotype_map": {  # 活性评分→表型
            (0, 0.5): ("PM", "差代谢者(Poor Metabolizer)"),
            (0.5, 1.0): ("IM", "中间代谢者(Intermediate Metabolizer)"),
            (1.0, 2.25): ("NM", "正常代谢者(Normal Metabolizer)"),
            (2.25, 3.0): ("UM", "超快代谢者(Ultrarapid Metabolizer)"),
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
            (0, 0.5): ("PM", "差代谢者(Poor Metabolizer)"),
            (0.5, 1.99): ("IM", "中间代谢者(Intermediate Metabolizer)"),
            (2.0, 2.49): ("NM", "正常代谢者(Normal Metabolizer)"),
            (2.5, 3.1): ("RM", "快速代谢者(Rapid Metabolizer)"),
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
            (0, 0.5): ("PM", "差代谢者"),
            (0.5, 1.0): ("IM", "中间代谢者"),
            (1.0, 2.0): ("NM", "正常代谢者"),
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
            (0, 0.5): ("高敏感性", "华法林高敏感性"),
            (0.5, 1.0): ("中等敏感性", "华法林中等敏感性"),
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
            (0, 0.5): ("PM", "差代谢者"),
            (0.5, 1.0): ("IM", "中间代谢者"),
            (1.0, 2.0): ("NM", "正常代谢者"),
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
            (0, 0.5): ("PM", "差代谢者"),
            (0.5, 1.0): ("IM", "中间代谢者"),
            (1.0, 2.0): ("NM", "正常代谢者"),
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
            (0.5, 1.0): ("中功能", "中等转运功能"),
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
            (0, 0.5): ("PM", "差代谢者"),
            (0.5, 1.0): ("IM", "中间代谢者"),
            (1.0, 2.0): ("NM", "正常代谢者"),
        },
        "drugs": [
            {"name": "伊立替康(Irinotecan)", "class": "化疗"},
            {"name": "阿扎那韦(Atazanavir)", "class": "抗HIV"},
        ],
    },
}


# 用药建议规则
DRUG_ADVICE = {
    "PM": {
        "advice": "避免使用或大幅降低剂量",
        "dose_adjustment": "考虑替代药物或剂量降至常规的25-50%",
        "monitoring": "密切监测药物不良反应",
    },
    "IM": {
        "advice": "适当降低剂量",
        "dose_adjustment": "剂量降至常规的50-75%",
        "monitoring": "监测疗效和不良反应",
    },
    "NM": {
        "advice": "正常剂量",
        "dose_adjustment": "按标准剂量给药",
        "monitoring": "常规监测",
    },
    "RM": {
        "advice": "可能需要增加剂量",
        "dose_adjustment": "考虑增加剂量或更换药物",
        "monitoring": "监测疗效，可能无效",
    },
    "UM": {
        "advice": "避免使用或增加剂量",
        "dose_adjustment": "可能无效，考虑替代药物或增加剂量",
        "monitoring": "密切监测疗效",
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

        # 确定表型 (左闭右闭区间)
        phenotype = "NM"
        phenotype_desc = "正常代谢者(Normal Metabolizer)"
        for (low, high), (ph, desc) in gene_rule["phenotype_map"].items():
            if low <= score <= high:
                phenotype = ph
                phenotype_desc = desc
                break

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
                    "activity_score": result.activity_score,
                    "drug_count": len(result.drug_recommendations),
                    "top_drugs": [d["drug_name"] for d in result.drug_recommendations[:3]],
                })

        logger.info(f"PGx analysis: {len(results)} genes interpreted from {len(variants)} variants")
        return results

    def get_drug_interactions(self, gene_results: list[dict]) -> list[dict]:
        """获取药物-基因相互作用摘要"""
        interactions = []
        for result in gene_results:
            gene = result.get("gene")
            genotype = result.get("genotype")
            if not gene or not genotype:
                continue

            pgx_result = self.interpret_genotype(gene, genotype)
            if pgx_result:
                for drug_rec in pgx_result.drug_recommendations:
                    if pgx_result.phenotype != "NM":  # 只报告非正常的
                        interactions.append({
                            "gene": gene,
                            "drug": drug_rec["drug_name"],
                            "drug_class": drug_rec["drug_class"],
                            "phenotype": pgx_result.phenotype,
                            "advice": drug_rec["advice"],
                            "severity": "high" if pgx_result.phenotype in ("PM", "UM") else "medium",
                        })

        return interactions
