"""融合诊断 API - 五层知识图谱因果链"""
from fastapi import APIRouter, Request

router = APIRouter(tags=["融合诊断"])


# ============ Demo 数据 ============

DEMO_FUSION_CHAIN = {
    "user_id": "demo",
    "layers": {
        "layer1_variants": [
            {
                "gene_symbol": "TP53",
                "rsid": "rs1042522",
                "hgvs": "NM_000546.5:c.215C>G",
                "clinical_significance": "Likely Pathogenic",
                "description": "肿瘤抑制基因TP53功能域变异，影响p53蛋白DNA结合能力",
                "allele_frequency": 0.023,
                "source": "ClinVar"
            },
            {
                "gene_symbol": "CYP2C19",
                "rsid": "rs4244285",
                "hgvs": "NM_000767.4:c.681G>A",
                "clinical_significance": "Benign",
                "description": "CYP2C19*2等位基因，影响氯吡格雷等药物代谢",
                "allele_frequency": 0.286,
                "source": "PharmGKB"
            },
            {
                "gene_symbol": "BRCA1",
                "rsid": "rs80357713",
                "hgvs": "NM_007294.3:c.5266dupC",
                "clinical_significance": "Pathogenic",
                "description": "BRCA1框移突变，导致同源重组修复功能丧失",
                "allele_frequency": 0.001,
                "source": "ClinVar"
            },
            {
                "gene_symbol": "NRF2",
                "rsid": "rs6721961",
                "hgvs": "NM_001313893.2:c.-617C>A",
                "clinical_significance": "Benign",
                "description": "NRF2启动子区变异，轻微影响Nrf2/Keap1抗氧化通路活性",
                "allele_frequency": 0.078,
                "source": "gnomAD"
            }
        ],
        "layer2_proteins": [
            {
                "gene_symbol": "TP53",
                "uniprot_id": "P04637",
                "protein_name": "Cellular tumor antigen p53",
                "function": "转录因子，调控细胞周期 arrest、DNA修复和凋亡",
                "pathways": ["hsa04115", "hsa04110"],
                "structure_source": "AlphaFold",
                "pdb_id": None,
                "interaction_partners": ["MDM2", "BAX", "CDKN1A"],
                "variant_impact": "p53蛋白DNA结合域结构不稳定，转录活性下降约60%"
            },
            {
                "gene_symbol": "BRCA1",
                "uniprot_id": "P38398",
                "protein_name": "Breast cancer type 1 susceptibility protein",
                "function": "DNA损伤修复（同源重组）、细胞周期检查点调控",
                "pathways": ["hsa03440", "hsa03430"],
                "structure_source": "PDB+AlphaFold",
                "pdb_id": "1JNX",
                "interaction_partners": ["BARD1", "RAD51", "PALB2"],
                "variant_impact": "BRCT功能域截短，无法招募RAD51进行同源重组修复"
            },
            {
                "gene_symbol": "NRF2",
                "uniprot_id": "Q16236",
                "protein_name": "Nuclear factor erythroid 2-related factor 2",
                "function": "抗氧化反应主调节因子，激活Nrf2/Keap1/ARE通路",
                "pathways": ["hsa04140"],
                "structure_source": "AlphaFold",
                "pdb_id": None,
                "interaction_partners": ["KEAP1", "MAFK", "ARE"],
                "variant_impact": "启动子活性轻微降低，Nrf2核转位效率下降约15%"
            }
        ],
        "layer3_pathways": [
            {
                "pathway_id": "hsa03440",
                "name": "Homologous Recombination",
                "display_name": "同源重组修复通路",
                "description": "高保真DNA双链断裂修复机制，BRCA1/2为核心蛋白",
                "category": "DNA_repair",
                "status": "downregulated",
                "score": 35,
                "severity": "严重",
                "related_genes": ["BRCA1", "BRCA2", "RAD51", "PALB2"],
                "tcm_bridge": "肾精不足 → 基因组不稳定 → 肾主生殖发育（先天之本）"
            },
            {
                "pathway_id": "hsa04115",
                "name": "p53 signaling pathway",
                "display_name": "p53信号通路",
                "description": "DNA损伤响应、细胞周期检查点和凋亡调控中枢",
                "category": "Apoptosis",
                "status": "downregulated",
                "score": 40,
                "severity": "中度",
                "related_genes": ["TP53", "MDM2", "CDKN1A", "BAX"],
                "tcm_bridge": "气虚证 → 细胞凋亡调控减弱 → 气不摄则脱"
            },
            {
                "pathway_id": "hsa04140",
                "name": "Autophagy - animal",
                "display_name": "自噬通路（含AMPK/mTOR）",
                "description": "AMPK激活自噬、mTOR抑制自噬的双向调控，影响细胞修复与衰老",
                "category": "AMPK",
                "status": "normal",
                "score": 68,
                "severity": "正常",
                "related_genes": ["AMPK", "mTOR", "SIRT1", "ULK1"],
                "tcm_bridge": "阴阳平衡 ↔ AMPK/mTOR能量感知双向调控"
            },
            {
                "pathway_id": "custom_nrf2",
                "name": "Nrf2/Keap1/ARE pathway",
                "display_name": "Nrf2抗氧化通路",
                "description": "抗氧化反应元件激活，清除ROS，保护细胞免受氧化损伤",
                "category": "Nrf2",
                "status": "slightly_downregulated",
                "score": 58,
                "severity": "轻微",
                "related_genes": ["NRF2", "KEAP1", "HO-1", "NQO1"],
                "tcm_bridge": "阴虚证 → 氧化应激 → Nrf2通路代偿上调不足"
            },
            {
                "pathway_id": "hsa04110",
                "name": "Cell Cycle",
                "display_name": "细胞周期通路",
                "description": "G1/S/G2/M检查点调控，p53为核心检查点守门人",
                "category": "cell_cycle",
                "status": "slightly_downregulated",
                "score": 55,
                "severity": "轻微",
                "related_genes": ["TP53", "CDKN1A", "CCND1", "RB1"],
                "tcm_bridge": "气滞证 ↔ 细胞增殖失控 ↔ 气机不畅"
            }
        ],
        "layer4_syndromes": [
            {
                "name": "气虚证",
                "description": "以气虚乏力、声低懒言、易出汗为主要表现的证候类型",
                "related_pathways": ["hsa04115", "hsa04110"],
                "score": 72,
                "confidence": "高",
                "modern_interpretation": "线粒体ATP生成效率降低，AMPK能量感知通路响应减弱",
                "key_evidence": "p53信号下调 + 细胞周期检查点减弱 → 细胞修复能力整体下降"
            },
            {
                "name": "肾精不足证",
                "description": "以生长发育迟缓、记忆力减退、腰膝酸软为表现的证候",
                "related_pathways": ["hsa03440"],
                "score": 85,
                "confidence": "高",
                "modern_interpretation": "DNA修复能力先天性缺陷，基因组稳定性维持能力降低",
                "key_evidence": "同源重组修复通路严重下调（评分35）→ 基因组损伤累积加速"
            },
            {
                "name": "阴虚证",
                "description": "以口干咽燥、五心烦热、潮热盗汗为表现的证候类型",
                "related_pathways": ["custom_nrf2"],
                "score": 58,
                "confidence": "中",
                "modern_interpretation": "Nrf2抗氧化通路代偿不足，ROS清除能力下降",
                "key_evidence": "Nrf2启动子变异导致核转位效率降低，抗氧化防御轻度受损"
            }
        ],
        "layer5_interventions": [
            {
                "intervention_type": "food_medicine",
                "name": "黄芪枸杞茶",
                "description": "黄芪30g、枸杞子15g，沸水冲泡代茶饮。黄芪甲苷通过PI3K/AKT通路保护血管内皮，枸杞多糖激活SIRT1延缓细胞衰老。",
                "target_pathways": ["hsa04115", "custom_nrf2"],
                "target_syndromes": ["气虚证", "阴虚证"],
                "active_compounds": ["黄芪甲苷(Astragaloside IV)", "枸杞多糖(LBP)", "环黄芪醇(CAG)"],
                "cell_repair_mechanism": "黄芪甲苷→PI3K/AKT通路→内皮保护；枸杞多糖→SIRT1去乙酰化→抗衰老",
                "evidence_level": "validated",
                "usage": "可以加入日常饮水，上班时泡一杯，不知不觉就喝完了",
                "timing": "不拘时候，随时饮用",
                "effort": "极低"
            },
            {
                "intervention_type": "food_medicine",
                "name": "人参山药薏米粥",
                "description": "人参片6g、山药20g、薏米30g、五味子5g、红枣5枚，煮粥。人参皂苷Rg1激活AMPK/mTOR通路促进细胞自噬清理，五味子木脂素激活Nrf2抗氧化防线。",
                "target_pathways": ["hsa04140", "custom_nrf2", "hsa04115"],
                "target_syndromes": ["气虚证", "阴虚证"],
                "active_compounds": ["人参皂苷Rg1(Ginsenoside Rg1)", "人参皂苷Rb1", "五味子甲素(Deoxyschisandrin)"],
                "cell_repair_mechanism": "人参皂苷Rg1→AMPK/mTOR→自噬激活；五味子木脂素→Nrf2/Keap1/ARE→抗氧化",
                "evidence_level": "validated",
                "usage": "可以拌在米饭里一起吃，也可以当早餐粥",
                "timing": "适合早餐或午餐",
                "effort": "低"
            },
            {
                "intervention_type": "gene_therapy",
                "name": "基因治疗咨询：BRCA1/2同源重组修复",
                "description": "基于BRCA1致病变异的基因治疗选项评估。当前CRISPR-Cas9基因编辑疗法（如Casgevy）已在镰状细胞病获批，BRCA相关基因治疗处于临床试验阶段。",
                "target_pathways": ["hsa03440"],
                "target_syndromes": ["肾精不足证"],
                "mechanism": "CRISPR-Cas9介导的精准基因编辑，修复或补偿BRCA1功能",
                "evidence_level": "preliminary",
                "action": "建议前往正规遗传咨询门诊进行专业评估",
                "contraindications": "目前尚无获批的BRCA基因治疗产品，仅供参考"
            },
            {
                "intervention_type": "targeted_drug",
                "name": "PARP抑制剂敏感性评估",
                "description": "BRCA1/2功能缺失的肿瘤细胞对PARP抑制剂（奥拉帕利）高度敏感——合成致死策略。此为临床已获批的精准治疗方案。",
                "target_pathways": ["hsa03440"],
                "target_syndromes": ["肾精不足证"],
                "mechanism": "PARP抑制剂阻断单链断裂修复，在BRCA缺陷细胞中引发合成致死",
                "evidence_level": "validated",
                "action": "如有相关肿瘤风险，由肿瘤科医生评估PARP抑制剂预防性使用"
            },
            {
                "intervention_type": "pharmacogenomic",
                "name": "CYP2C19药物代谢指导",
                "description": "您携带CYP2C19*2等位基因（慢代谢型），影响氯吡格雷、质子泵抑制剂等药物代谢。建议与医生沟通替代方案。",
                "target_pathways": [],
                "target_syndromes": [],
                "gene_variants": ["CYP2C19"],
                "recommendation": "氯吡格雷：建议换用替格瑞洛（不受CYP2C19影响）",
                "evidence_level": "validated",
                "source": "PharmGKB/CPIC"
            }
        ]
    },
    "summary": {
        "total_variants": 4,
        "pathogenic_count": 1,
        "benign_count": 2,
        "likely_pathogenic_count": 1,
        "pathway_abnormal_count": 3,
        "dominant_syndrome": "气虚证 + 肾精不足证",
        "repair_chain_summary": "BRCA1致病变异→同源重组修复严重缺陷→肾精不足证；TP53变异→p53信号下调→气虚证。核心方向：人参黄芪类药食同源激活AMPK/Nrf2通路进行日常修复；基因治疗和PARP抑制剂作为临床级别选项留存。",
        "evidence_note": "本分析基于ClinVar/PharmGKB/gnomAD数据库注释 + TCMSP成分靶点数据。细胞通路评分为模型估算。本方案为健康养生建议，不构成医疗建议。"
    }
}


# ============ API Endpoints ============

# 诚实原则：DEMO_FUSION_CHAIN 仅用于「未登录预览 / 示例展示」，
# 绝不伪装成已登录用户的真实分析。任何返回都显式标注 is_demo=True，
# 真实分析请调用 /api/v1/diagnosis-agent 并传入用户自己的基因/检验/中医症状。
_DEMO_NOTE = "示例数据（非个人真实分析）。真实五层因果链请调用 /api/v1/diagnosis-agent 并上传您本人的基因/检验/中医症状数据。"


def _demo_response(data: dict) -> dict:
    return {
        "success": True,
        "demo": True,
        "is_demo": True,
        "note": _DEMO_NOTE,
        "data": data,
    }


@router.get("/chain")
async def get_fusion_chain(request: Request):
    """获取完整五层因果链（示例数据，仅用于预览）"""
    return _demo_response(DEMO_FUSION_CHAIN)


@router.get("/pathways")
async def get_fusion_pathways(request: Request):
    """获取第三层细胞通路数据（示例数据，仅用于预览）"""
    return _demo_response(DEMO_FUSION_CHAIN["layers"]["layer3_pathways"])


@router.get("/interventions")
async def get_fusion_interventions(request: Request):
    """获取第五层治疗干预数据（示例数据，仅用于预览）"""
    return _demo_response(DEMO_FUSION_CHAIN["layers"]["layer5_interventions"])