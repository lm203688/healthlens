"""SEO 内容工厂模型 - 页面、模板、关键词聚类"""
from datetime import datetime
from sqlalchemy import String, DateTime, Text, JSON, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class SeoPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SEO 页面内容"""
    __tablename__ = "seo_pages"

    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    meta_description: Mapped[str] = mapped_column(String(1000))
    meta_keywords: Mapped[str] = mapped_column(String(500))
    content_html: Mapped[str] = mapped_column(Text)
    structured_data: Mapped[dict | None] = mapped_column(JSON)
    category: Mapped[str] = mapped_column(String(100), index=True)
    heading: Mapped[str | None] = mapped_column(String(500))
    keywords: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft"
    )  # draft / published / archived
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)


class SeoPageTemplate(UUIDPrimaryKeyMixin, Base):
    """SEO 页面模板"""
    __tablename__ = "seo_page_templates"

    template_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    template_html: Mapped[str] = mapped_column(Text)
    schema_types: Mapped[list | None] = mapped_column(JSON)
    category: Mapped[str] = mapped_column(String(100), index=True)
    created_at = mapped_column(DateTime, server_default="now()")


class KeywordCluster(UUIDPrimaryKeyMixin, Base):
    """关键词聚类"""
    __tablename__ = "keyword_clusters"

    keyword: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    search_volume: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[int | None] = mapped_column(Integer)  # 1-100
    intent: Mapped[str] = mapped_column(
        String(20)
    )  # informational / commercial / transactional
    category: Mapped[str] = mapped_column(String(100), index=True)
    related_keywords: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_at = mapped_column(DateTime, server_default="now()")

    __table_args__ = (
        Index("ix_keyword_clusters_category_status", "category", "status"),
    )
