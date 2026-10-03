"""自动化获客 Celery 定时任务
调度方式: celery -A app.worker.celery_app beat --loglevel=info
"""
from loguru import logger
from app.worker import celery_app
import asyncio


@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def seo_batch_generate(task_self, count: int = 10, category: str = "conditions"):
    """批量生成 SEO 知识页面（从内容工厂填充真实内容）
    周三/周六 03:00 触发
    """
    async def _run():
        from app.database import SessionLocal
        from app.services.seo_factory import SeoContentFactory
        from app.models.seo import SeoPage
        from sqlalchemy import select, func

        db = SessionLocal()
        try:
            factory = SeoContentFactory()

            # 使用 batch_generate 的 include_html 模式
            pages = factory.batch_generate(count=count, category=category, include_html=True)

            created = 0
            updated = 0
            for page_data in pages:
                if not page_data.get("slug") or not page_data.get("content_html"):
                    continue

                slug = page_data["slug"][:200]

                # 检查是否已存在
                existing = await db.execute(
                    select(SeoPage).where(SeoPage.slug == slug)
                )
                seo_page = existing.scalar_one_or_none()

                if seo_page:
                    # 更新内容
                    seo_page.title = page_data.get("title", slug)
                    seo_page.content_html = page_data["content_html"]
                    seo_page.meta_description = page_data.get("meta_description", "")
                    seo_page.meta_keywords = page_data.get("meta_keywords", "")
                    seo_page.word_count = page_data.get("word_count", 0)
                    seo_page.updated_at = func.now()
                    updated += 1
                else:
                    # 新建
                    new_page = SeoPage(
                        slug=slug,
                        title=page_data.get("title", slug),
                        category=category,
                        status="draft",
                        meta_description=page_data.get("meta_description", ""),
                        meta_keywords=page_data.get("meta_keywords", ""),
                        content_html=page_data["content_html"],
                        word_count=page_data.get("word_count", 0),
                        structured_data=page_data.get("structured_data"),
                    )
                    db.add(new_page)
                    created += 1

                if (created + updated) % 5 == 0:
                    await db.commit()

            await db.commit()

            logger.info(
                f"[SEO Batch] category={category}, "
                f"created={created}, updated={updated}, total={len(pages)}"
            )
            return {
                "success": True,
                "created": created,
                "updated": updated,
                "total": len(pages),
                "category": category,
            }
        except Exception as e:
            logger.error(f"[SEO Batch] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"seo_batch_generate task failed: {exc}")
        raise task_self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=300)
def seo_auto_publish(task_self, max_pages: int = 10):
    """自动审核并发布 SEO 页面（质量检查后发布 + Sitemap 刷新）
    每日 04:00 触发，按 herbs → conditions → education 优先级发布
    """
    # 分类优先级（优先发布内容质量高的分类）
    CATEGORY_PRIORITY = ["herbs", "conditions", "education"]

    async def _run():
        from app.database import SessionLocal
        from app.models.seo import SeoPage
        from sqlalchemy import select, and_, func, case
        from datetime import datetime

        db = SessionLocal()
        try:
            # 按分类优先级分批查找待发布草稿（有内容且字数>=300）
            # 使用 CASE 表达式实现优先级排序
            priority_expr = case(
                *[(
                    SeoPage.category == cat, idx
                ) for idx, cat in enumerate(CATEGORY_PRIORITY)],
                else_=99
            )

            result = await db.execute(
                select(SeoPage).where(
                    and_(
                        SeoPage.status == "draft",
                        SeoPage.word_count >= 300,
                        SeoPage.content_html.isnot(None),
                    )
                ).order_by(
                    priority_expr.asc(),
                    SeoPage.word_count.desc(),
                    SeoPage.created_at.asc()
                ).limit(max_pages)
            )
            draft_pages = result.scalars().all()

            published = 0
            category_stats = {}
            for page in draft_pages:
                page.status = "published"
                page.published_at = datetime.utcnow()
                published += 1
                cat = page.category or "other"
                category_stats[cat] = category_stats.get(cat, 0) + 1

            await db.commit()

            # 统计发布后的总量
            total_published_result = await db.execute(
                select(func.count()).select_from(SeoPage).where(SeoPage.status == "published")
            )
            total_published = total_published_result.scalar() or 0

            # 剩余草稿数
            remaining_result = await db.execute(
                select(func.count()).select_from(SeoPage).where(SeoPage.status == "draft")
            )
            remaining = remaining_result.scalar() or 0

            stats_str = ", ".join(f"{k}={v}" for k, v in sorted(category_stats.items()))
            logger.info(
                f"[SEO Publish] Published {published} pages ({stats_str}), "
                f"total_published={total_published}, drafts_remaining={remaining}"
            )

            return {
                "success": True,
                "published": published,
                "by_category": category_stats,
                "total_published": total_published,
                "drafts_remaining": remaining,
            }
        except Exception as e:
            logger.error(f"[SEO Publish] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"seo_auto_publish task failed: {exc}")
        raise task_self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=300)
def cleanup_expired_invites(task_self):
    """清理过期邀请码
    每日 05:00 触发
    """
    async def _run():
        from app.database import SessionLocal
        from app.services.referral_service import cleanup_expired_codes

        db = SessionLocal()
        try:
            result = await cleanup_expired_codes(db)
            logger.info(f"[Cleanup] Expired invites: {result.get('expired_count', 0)}")
            return result
        except Exception as e:
            logger.error(f"[Cleanup] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"cleanup_expired_invites failed: {exc}")
        raise task_self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=300)
def cleanup_old_analytics(task_self, days: int = 90):
    """清理过期分析事件数据
    每周日 05:00 触发
    """
    async def _run():
        from app.database import SessionLocal
        from app.services.analytics_service import cleanup_old_events

        db = SessionLocal()
        try:
            result = await cleanup_old_events(db, days=days)
            logger.info(f"[Cleanup] Old analytics removed: {result}")
            return {"success": True, "cleaned": result}
        except Exception as e:
            logger.error(f"[Cleanup] Old analytics failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"cleanup_old_analytics failed: {exc}")
        raise task_self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=300)
def acquisition_weekly_report(task_self):
    """获客数据周报
    每周一 04:00 触发
    """
    async def _run():
        from app.database import SessionLocal
        from app.services.analytics_service import get_dashboard_stats, get_funnel_stats, get_channel_stats
        from app.models.seo import SeoPage
        from sqlalchemy import select, func, and_
        from datetime import datetime, timedelta
        import json

        db = SessionLocal()
        try:
            # 1. 基础数据
            dashboard = await get_dashboard_stats(db, days=7)
            funnel = await get_funnel_stats(db)

            try:
                channels = await get_channel_stats(db, days=7)
            except:
                channels = {}

            # 2. SEO 数据
            total_pages_result = await db.execute(
                select(func.count()).select_from(SeoPage)
            )
            total_pages = total_pages_result.scalar() or 0

            published_result = await db.execute(
                select(func.count()).select_from(SeoPage).where(SeoPage.status == "published")
            )
            published_pages = published_result.scalar() or 0

            # 3. 本周新增
            week_ago = datetime.utcnow() - timedelta(days=7)
            new_result = await db.execute(
                select(func.count()).select_from(SeoPage).where(SeoPage.created_at >= week_ago)
            )
            new_pages = new_result.scalar() or 0

            report = {
                "report_type": "acquisition_weekly",
                "period": "7 days",
                "generated_at": datetime.utcnow().isoformat(),
                "dashboard": dashboard,
                "funnel": funnel,
                "channels": channels,
                "seo": {
                    "total_pages": total_pages,
                    "published_pages": published_pages,
                    "new_pages_this_week": new_pages,
                },
            }

            # 保存到文件
            try:
                import os
                reports_dir = "/opt/healthlens/reports"
                os.makedirs(reports_dir, exist_ok=True)
                filename = f"acquisition_weekly_{datetime.utcnow().strftime('%Y%m%d')}.json"
                filepath = os.path.join(reports_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, default=str)
                logger.info(f"[Weekly Report] Saved to {filepath}")
            except Exception as e:
                logger.warning(f"[Weekly Report] Failed to save file: {e}")

            logger.info(
                f"[Weekly Report] DAU={dashboard.get('dau', 0)}, "
                f"SEO published={published_pages}, new pages={new_pages}"
            )

            return {"success": True, "report": report}
        except Exception as e:
            logger.error(f"[Weekly Report] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"acquisition_weekly_report failed: {exc}")
        raise task_self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=300)
def user_education_push(task_self):
    """用户教育内容生成（四级认知阶梯）
    每周五 03:00 触发
    """
    async def _run():
        from app.database import SessionLocal
        from app.services.seo_factory import SeoContentFactory
        from app.models.seo import SeoPage
        from sqlalchemy import select

        db = SessionLocal()
        try:
            factory = SeoContentFactory()
            # 生成教育类内容
            pages = factory.batch_generate(count=5, category="education", include_html=True)

            from app.models.seo import SeoPage
            from sqlalchemy import select

            created = 0
            for page_data in pages:
                if not page_data.get("slug"):
                    continue
                existing = await db.execute(
                    select(SeoPage).where(SeoPage.slug == page_data["slug"][:200])
                )
                if not existing.scalar_one_or_none():
                    new_page = SeoPage(
                        slug=page_data["slug"][:200],
                        title=page_data.get("title", ""),
                        category="education",
                        status="draft",
                        meta_description=page_data.get("meta_description", ""),
                        meta_keywords=page_data.get("meta_keywords", ""),
                        content_html=page_data.get("content_html", ""),
                        word_count=page_data.get("word_count", 0),
                        structured_data=page_data.get("structured_data"),
                    )
                    db.add(new_page)
                    created += 1

            await db.commit()
            logger.info(f"[Education Push] Generated {created} education pages")
            return {"success": True, "created": created}
        except Exception as e:
            logger.error(f"[Education Push] Failed: {e}")
            raise
        finally:
            db.close()

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        logger.error(f"user_education_push failed: {exc}")
        raise task_self.retry(exc=exc)
