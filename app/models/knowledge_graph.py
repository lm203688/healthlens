"""五层知识图谱数据模型 - 融合诊断核心"""
from sqlalchemy import String, Text, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class GeneVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """第一层：基因变异层"""
    __tablename__ = "gene_variants"

    user_id: Mapped[str] = mapped_column(String(36), index=True)
    rsid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hgvs_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gene_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    chromosome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_allele: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alt_allele: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clinical_significance: Mapped[str | None] = mapped_column(String(50), nullable=True)
    clinvar_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    allele_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ProteinAnnotation(UUIDPrimaryKeyMixin, Base):
    """第二层：蛋白质功能注释层"""
    __tablename__ = "protein_annotations"

    gene_symbol: Mapped[str] = mapped_column(String(50), index=True)
    uniprot_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    protein_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    function_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pathway_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    structure_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pdb_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    interaction_partners: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_by_variants: Mapped[list | None] = mapped_column(JSON, nullable=True)


class CellularPathway(UUIDPrimaryKeyMixin, Base):
    """第三层：细胞通路层（中枢层）"""
    __tablename__ = "cellular_pathways"

    pathway_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pathway_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    related_genes: Mapped[list] = mapped_column(JSON, nullable=False)
    related_proteins: Mapped[list] = mapped_column(JSON, nullable=False)
    related_syndromes: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(20), nullable=False)


class TcmSyndromeMapping(UUIDPrimaryKeyMixin, Base):
    """第四层：中医证候映射层"""
    __tablename__ = "tcm_syndrome_mappings"

    syndrome_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_pathways: Mapped[list | None] = mapped_column(JSON, nullable=True)
    related_herbs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    modern_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_target_description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TherapeuticIntervention(UUIDPrimaryKeyMixin, Base):
    """第五层：治疗干预层"""
    __tablename__ = "therapeutic_interventions"

    intervention_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_pathways: Mapped[list] = mapped_column(JSON, nullable=False)
    target_syndromes: Mapped[list] = mapped_column(JSON, nullable=False)
    active_compounds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_level: Mapped[str] = mapped_column(String(20), nullable=False)
    contraindications: Mapped[str | None] = mapped_column(Text, nullable=True)