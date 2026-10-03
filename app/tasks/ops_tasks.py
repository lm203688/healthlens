"""运维类 Celery 任务（2026-08-04 新增）

解决的问题：此前系统没有任何「任务是否真的在跑」的证据。
Beat 服务从未部署，9 个定时任务一次都没执行过，但没有任何机制能发现这件事。

本模块提供两个基础能力：
  1. write_heartbeat  —— 周期性写心跳，让外部看门狗能判定 beat 是否存活
  2. run_selfcheck    —— 自检数据库/Redis 连通性，异常时留下可被发现的证据

心跳同时写两处：
  - Redis key（快，供 /health 端点即时读取）
  - 本地文件（持久，容器重启/Redis 清空后仍可追溯最后存活时间）
"""
import gzip
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta

from loguru import logger

from app.worker import celery_app

CST = timezone(timedelta(hours=8))

HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/app/data/heartbeat.json")
HEARTBEAT_REDIS_KEY = "healthlens:beat:heartbeat"
# 心跳 30 分钟未更新即视为 beat 已死（调度间隔 10 分钟，容忍 2 次丢失）
HEARTBEAT_TTL_SECONDS = 1800

# 数据库逻辑备份（T3）
BACKUP_DIR = os.getenv("BACKUP_DIR", "/app/data/backups")
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "7"))
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "pg_dump")


def _now_iso() -> str:
    return datetime.now(CST).isoformat()


def _write_heartbeat_file(payload: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
        # 先写临时文件再原子替换，避免看门狗读到写了一半的 JSON
        tmp = f"{HEARTBEAT_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, HEARTBEAT_FILE)
        return True
    except Exception as e:
        logger.error(f"[heartbeat] 写文件失败: {e}")
        return False


def _write_heartbeat_redis(payload: dict) -> bool:
    try:
        import redis
        from app.config import settings

        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5)
        client.setex(
            HEARTBEAT_REDIS_KEY,
            HEARTBEAT_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )
        return True
    except Exception as e:
        logger.error(f"[heartbeat] 写 Redis 失败: {e}")
        return False


@celery_app.task(name="app.tasks.ops_tasks.write_heartbeat")
def write_heartbeat():
    """写 beat 心跳。每 10 分钟一次。

    这个任务本身必须极简且几乎不可能失败——它是判定「其他任务有没有在跑」
    的基准信号，如果它自己容易挂，整个看门狗就失去意义。
    """
    payload = {
        "timestamp": _now_iso(),
        "unix": int(datetime.now(CST).timestamp()),
        "source": "celery-beat",
        "hostname": os.getenv("HOSTNAME", "unknown"),
    }

    file_ok = _write_heartbeat_file(payload)
    redis_ok = _write_heartbeat_redis(payload)

    # 两个通道都失败才算任务失败——单通道降级不影响判活
    if not file_ok and not redis_ok:
        logger.error("[heartbeat] 文件与 Redis 双通道均写入失败")
        raise RuntimeError("heartbeat write failed on both channels")

    logger.info(f"[heartbeat] ok file={file_ok} redis={redis_ok}")
    return {"ok": True, "file": file_ok, "redis": redis_ok, "ts": payload["timestamp"]}


@celery_app.task(name="app.tasks.ops_tasks.run_selfcheck", bind=True, max_retries=1)
def run_selfcheck(self):
    """自检核心依赖连通性，结果落盘供 /health 与外部看门狗读取。

    与 write_heartbeat 的区别：心跳只证明「调度器活着」，
    自检证明「依赖可用」。两者缺一不可——beat 活着但数据库连不上，
    业务任务依然全军覆没。
    """
    results = {"checked_at": _now_iso(), "checks": {}}

    # --- 数据库 ---
    try:
        from sqlalchemy import text
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            results["checks"]["database"] = {"status": "ok"}
        finally:
            db.close()
    except Exception as e:
        results["checks"]["database"] = {"status": "error", "error": str(e)[:300]}

    # --- Redis ---
    try:
        import redis
        from app.config import settings

        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5)
        client.ping()
        results["checks"]["redis"] = {"status": "ok"}
    except Exception as e:
        results["checks"]["redis"] = {"status": "error", "error": str(e)[:300]}

    # --- Celery worker ---
    try:
        replies = celery_app.control.ping(timeout=3)
        worker_count = len(replies) if replies else 0
        results["checks"]["celery_workers"] = {
            "status": "ok" if worker_count > 0 else "error",
            "count": worker_count,
        }
    except Exception as e:
        results["checks"]["celery_workers"] = {"status": "error", "error": str(e)[:300]}

    failed = [k for k, v in results["checks"].items() if v.get("status") != "ok"]
    results["overall"] = "healthy" if not failed else "degraded"
    results["failed_checks"] = failed

    try:
        path = os.getenv("SELFCHECK_FILE", "/app/data/selfcheck.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[selfcheck] 结果落盘失败: {e}")

    if failed:
        # 主动抛错，让失败在 Celery 结果里留痕，而不是静默返回 degraded
        logger.error(f"[selfcheck] 依赖异常: {failed}")
        raise RuntimeError(f"selfcheck failed: {failed}")

    logger.info("[selfcheck] 全部依赖正常")
    return results


@celery_app.task(name="app.tasks.ops_tasks.backup_database", bind=True, max_retries=1)
def backup_database(self):
    """每日数据库逻辑备份（pg_dump -> gzip），落盘到 BACKUP_DIR。

    命名格式 healthlens_YYYY-MM-DD_HHMMSS.sql.gz，保留最近 BACKUP_KEEP 份（默认7）。
    非 postgres 库（如测试用 sqlite）仅记录、不报错，避免误杀 beat 调度。
    """
    from app.config import settings

    url = settings.DATABASE_URL
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(CST).strftime("%Y-%m-%d_%H%M%S")

    if url.startswith("postgresql"):
        out_path = os.path.join(BACKUP_DIR, f"healthlens_{ts}.sql.gz")
        env = dict(os.environ)
        try:
            cmd = [PG_DUMP_PATH, "--no-owner", "--clean", "--if-exists", url]
            # GzipFile 直接打开目标文件，pg_dump 的 stdout 经管道写入
            with gzip.GzipFile(filename=out_path, mode="wb") as gz:
                proc = subprocess.run(
                    cmd, stdout=gz, stderr=subprocess.PIPE, env=env, timeout=1800
                )
            if proc.returncode != 0:
                msg = proc.stderr.decode("utf-8", "ignore")[:500]
                logger.error(f"[backup] pg_dump 失败: {msg}")
                try:
                    os.remove(out_path)
                except OSError:
                    pass
                raise RuntimeError(f"pg_dump failed: {msg}")
            logger.info(f"[backup] ok -> {out_path}")
        except FileNotFoundError:
            logger.error("[backup] 未找到 pg_dump，跳过（请在生产镜像安装 postgresql-client）")
            return {"ok": False, "reason": "pg_dump_not_found"}
    else:
        # 测试/本地 sqlite 场景：不执行逻辑备份，仅留痕
        logger.info(f"[backup] 非 postgres 库（{url[:20]}...），跳过逻辑备份")
        return {"ok": False, "reason": "unsupported_db_type"}

    # 旋转：仅保留最近 BACKUP_KEEP 份
    try:
        files = sorted(
            f
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("healthlens_") and f.endswith(".sql.gz")
        )
        for old in files[:-BACKUP_KEEP]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except OSError:
                pass
    except Exception as e:  # 旋转失败不影响本次备份结果
        logger.warning(f"[backup] 旋转旧备份失败: {e}")

    return {"ok": True, "path": out_path, "kept": BACKUP_KEEP}
