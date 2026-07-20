"""中医古籍知识库模型 - 食疗、古籍方剂、非药物治疗"""
from datetime import datetime
from sqlalchemy import String, Text, JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class TcmClassicalBook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """中医古籍书目"""
    __tablename__ = "tcm_classical_books"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    dynasty: Mapped[str | None] = mapped_column(String(100))  # 朝代
    year_text: Mapped[str | None] = mapped_column(String(200))  # 年份描述
    category: Mapped[str | None] = mapped_column(String(100))  # 本草/方剂/食疗/针灸/综合
    description: Mapped[str | None] = mapped_column(Text)


class FoodTherapyRecipe(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """食疗方 - 来自古籍的食疗配方"""
    __tablename__ = "food_therapy_recipes"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_book: Mapped[str | None] = mapped_column(String(200))  # 出处
    dynasty: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))  # 分类(粥/羹/汤/酒/丸/散)
    ingredients: Mapped[dict | None] = mapped_column(JSON)  # 食材 {"食品": "大萝卜五个"}
    indications: Mapped[str | None] = mapped_column(Text)  # 主疗症状
    method: Mapped[str | None] = mapped_column(Text)  # 制法用法
    constitution_types: Mapped[dict | None] = mapped_column(JSON)  # 适用体质 ["qixu", "yangxu"]
    syndrome_keywords: Mapped[dict | None] = mapped_column(JSON)  # 适用的证型关键词 ["消渴", "口干"]
    seasonal: Mapped[str | None] = mapped_column(String(50))  # 适用季节 spring/summer/autumn/winter/all


class ClassicalFormula(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """古籍经典方剂"""
    __tablename__ = "classical_formulas"

    formula_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_book: Mapped[str | None] = mapped_column(String(200))
    dynasty: Mapped[str | None] = mapped_column(String(100))
    composition: Mapped[dict | None] = mapped_column(JSON)  # 组方 {"黄芪": "三两", "当归": "二两"}
    indications: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)  # 煎服法
    syndrome_code: Mapped[str | None] = mapped_column(String(50))
    constitution_types: Mapped[dict | None] = mapped_column(JSON)
    modifications: Mapped[dict | None] = mapped_column(JSON)  # 加减法
    classical_reference: Mapped[str | None] = mapped_column(Text)  # 原文摘录


class NonPharmaTreatment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """非药物治疗方案 - 食疗/针灸/推拿/导引/情志/起居"""
    __tablename__ = "non_pharma_treatments"

    treatment_type: Mapped[str] = mapped_column(String(50), nullable=False)  # diet/acupressure/massage/qigong/lifestyle
    treatment_type_name: Mapped[str | None] = mapped_column(String(100))  # 食疗/穴位按压/推拿/气功/起居调养
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_book: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)  # 详细方法
    indications: Mapped[str | None] = mapped_column(Text)  # 适应症状
    constitution_types: Mapped[dict | None] = mapped_column(JSON)
    syndrome_keywords: Mapped[dict | None] = mapped_column(JSON)
    instructions: Mapped[dict | None] = mapped_column(JSON)  # 具体操作步骤
    frequency: Mapped[str | None] = mapped_column(String(100))  # 频率
    duration: Mapped[str | None] = mapped_column(String(100))  # 疗程
    precautions: Mapped[str | None] = mapped_column(Text)  # 注意事项