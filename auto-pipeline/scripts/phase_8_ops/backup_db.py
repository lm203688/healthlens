"""T3 数据库备份 + 恢复验证（2026-08-04 新增）

背景
----
原系统有 6 条闭环、9 个 Celery 任务，唯独没有备份。
对一个存放健康检测数据的平台来说，这是比宕机严重得多的风险：
宕机能恢复，数据丢了就永远回不来。

关键设计：**没有验证过的备份等于没有备份**
------------------------------------------
绝大多数备份方案的失败模式不是"没备份"，而是"备份文件是空的/损坏的，
但没人知道，直到需要恢复的那天"。所以本脚本强制走完四步：

    1. dump      —— 导出
    2. size check—— 大小合理性（空转储通常只有几百字节）
    3. integrity —— gzip 完整性 + SQL 结构特征校验
    4. restore   —— 真实恢复到临时库并计数表数量（最强验证）

第 4 步失败会告警。任何一步失败都不允许静默通过。

支持三种模式（config.backup.mode）：
  ssh          —— 远程服务器 docker exec pg_dump，scp 回本地
  local_docker —— 本机 docker exec pg_dump
  auto         —— 先试 ssh，不通再试 local_docker
"""
import gzip
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from alerting import LEVEL_CRITICAL, resolve_alert, send_alert
from state_manager import BASE_DIR, get_state, log, save_state

ALERT_KEY = "backup:failed"


def _cfg() -> dict:
    with open(BASE_DIR / "config.json", encoding="utf-8") as f:
        return json.load(f).get("backup", {})


def _run(cmd, timeout=900, shell=False):
    try:
        r = subprocess.run(cmd, shell=shell, capture_output=True,
                           timeout=timeout)
        return r.returncode, r.stdout, (r.stderr or b"").decode("utf-8", "replace")[:500]
    except subprocess.TimeoutExpired:
        return -1, b"", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return -2, b"", f"命令不存在: {e}"
    except Exception as e:
        return -3, b"", str(e)[:300]


# --------------------------------------------------------------------------
# 步骤 1: 导出
# --------------------------------------------------------------------------
def dump_via_ssh(cfg, out_path):
    host = cfg.get("ssh_host", "")
    container = cfg.get("db_container", "healthlens-db")
    user = cfg.get("db_user", "healthlens")
    db = cfg.get("db_name", "healthlens")
    if not host:
        return False, "未配置 ssh_host"

    remote_cmd = f"docker exec {container} pg_dump -U {user} -d {db} --clean --if-exists"
    code, stdout, stderr = _run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=15", host, remote_cmd],
        timeout=1800,
    )
    if code != 0:
        return False, f"SSH pg_dump 失败 (exit {code}): {stderr}"
    if not stdout or len(stdout) < 100:
        return False, f"pg_dump 输出过小 ({len(stdout)} 字节)，疑似空转储"

    with gzip.open(out_path, "wb") as f:
        f.write(stdout)
    return True, ""


def dump_via_local_docker(cfg, out_path):
    container = cfg.get("db_container", "healthlens-db")
    user = cfg.get("db_user", "healthlens")
    db = cfg.get("db_name", "healthlens")

    code, _, stderr = _run(["docker", "inspect", "-f", "{{.State.Running}}", container], timeout=30)
    if code != 0:
        return False, f"本机无容器 {container}: {stderr}"

    code, stdout, stderr = _run(
        ["docker", "exec", container, "pg_dump", "-U", user, "-d", db, "--clean", "--if-exists"],
        timeout=1800,
    )
    if code != 0:
        return False, f"本机 pg_dump 失败 (exit {code}): {stderr}"
    if not stdout or len(stdout) < 100:
        return False, f"pg_dump 输出过小 ({len(stdout)} 字节)"

    with gzip.open(out_path, "wb") as f:
        f.write(stdout)
    return True, ""


def do_dump(cfg, out_path):
    mode = cfg.get("mode", "auto")
    errors = []

    if mode in ("ssh", "auto"):
        ok, err = dump_via_ssh(cfg, out_path)
        if ok:
            return True, "ssh", ""
        errors.append(f"ssh: {err}")

    if mode in ("local_docker", "auto"):
        ok, err = dump_via_local_docker(cfg, out_path)
        if ok:
            return True, "local_docker", ""
        errors.append(f"local_docker: {err}")

    return False, mode, " | ".join(errors)


# --------------------------------------------------------------------------
# 步骤 2 & 3: 大小 + 完整性校验
# --------------------------------------------------------------------------
def verify_file(path, cfg):
    """校验备份文件本身是否可用。

    只看文件存在是不够的——pg_dump 失败时经常也会产生一个小文件。
    """
    checks = {}
    min_size = cfg.get("min_valid_size_bytes", 1024)

    if not path.exists():
        return False, {"exists": False}, "备份文件不存在"

    size = path.stat().st_size
    checks["size_bytes"] = size
    checks["size_ok"] = size >= min_size
    if not checks["size_ok"]:
        return False, checks, f"备份文件仅 {size} 字节，小于阈值 {min_size}"

    # gzip 完整性：能完整解压说明没截断
    try:
        total = 0
        head = b""
        with gzip.open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 256)
                if not chunk:
                    break
                if not head:
                    head = chunk[:4096]
                total += len(chunk)
        checks["gzip_ok"] = True
        checks["uncompressed_bytes"] = total
    except Exception as e:
        checks["gzip_ok"] = False
        return False, checks, f"gzip 校验失败（文件可能截断）: {str(e)[:200]}"

    # SQL 结构特征：真实 pg_dump 一定带这些标记
    text = head.decode("utf-8", "replace")
    checks["has_pg_dump_header"] = "PostgreSQL database dump" in text
    if not checks["has_pg_dump_header"]:
        return False, checks, "文件头不含 pg_dump 标记，可能不是有效转储"

    return True, checks, ""


# --------------------------------------------------------------------------
# 步骤 4: 真实恢复验证（最强验证）
# --------------------------------------------------------------------------
def verify_restore(path, cfg):
    """把备份恢复到一个临时数据库，确认它真的能用。

    这一步是区分「有备份文件」和「有可用备份」的分水岭。
    如果环境不具备（无 docker/无 ssh），如实返回 skipped，
    绝不伪装成通过——那正是原系统犯的错。
    """
    container = cfg.get("db_container", "healthlens-db")
    user = cfg.get("db_user", "healthlens")
    tmp_db = f"restore_verify_{datetime.now().strftime('%H%M%S')}"

    code, _, _ = _run(["docker", "inspect", "-f", "{{.State.Running}}", container], timeout=30)
    if code != 0:
        return None, "本机无数据库容器，跳过恢复验证（备份文件校验已通过）"

    try:
        code, _, stderr = _run(
            ["docker", "exec", container, "createdb", "-U", user, tmp_db], timeout=60)
        if code != 0:
            return False, f"创建临时库失败: {stderr}"

        with gzip.open(path, "rb") as f:
            sql = f.read()

        p = subprocess.run(
            ["docker", "exec", "-i", container, "psql", "-U", user, "-d", tmp_db, "-q"],
            input=sql, capture_output=True, timeout=900,
        )
        if p.returncode != 0:
            return False, f"恢复失败: {(p.stderr or b'').decode('utf-8', 'replace')[:300]}"

        code, out, _ = _run(
            ["docker", "exec", container, "psql", "-U", user, "-d", tmp_db, "-t", "-c",
             "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],
            timeout=60,
        )
        table_count = int(out.decode().strip() or 0) if code == 0 else 0
        if table_count < 5:
            return False, f"恢复后仅 {table_count} 张表，明显不完整"
        return True, f"恢复验证通过：{table_count} 张表"
    finally:
        _run(["docker", "exec", container, "dropdb", "-U", user, "--if-exists", tmp_db], timeout=60)


# --------------------------------------------------------------------------
# 保留策略
# --------------------------------------------------------------------------
def apply_retention(backup_dir, days):
    """清理过期备份。注意只删本脚本自己生成的命名格式，不碰其他文件。"""
    cutoff = datetime.now() - timedelta(days=days)
    removed = []
    for f in backup_dir.glob("healthlens_*.sql.gz"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed.append(f.name)
        except Exception as e:
            log(f"清理备份 {f.name} 失败: {e}", level="WARN")
    return removed


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run():
    cfg = _cfg()
    if not cfg.get("enabled", True):
        log("备份已在配置中禁用，跳过")
        return True

    backup_dir = BASE_DIR / cfg.get("local_backup_dir", "backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = backup_dir / f"healthlens_{ts}.sql.gz"

    result = {
        "backup_id": f"bk_{ts}",
        "started_at": datetime.now().isoformat(),
        "file": str(out_path.relative_to(BASE_DIR)),
        "steps": {},
    }

    log("=" * 60)
    log("T3 数据库备份 + 恢复验证")
    log("=" * 60)

    # --- 1. 导出 ---
    ok, mode, err = do_dump(cfg, out_path)
    result["mode"] = mode
    result["steps"]["dump"] = {"ok": ok, "error": err}
    if not ok:
        log(f"备份导出失败: {err}", level="ERROR")
        if out_path.exists():
            out_path.unlink()
        result["status"] = "failed"
        result["finished_at"] = datetime.now().isoformat()
        _persist(result)
        send_alert(
            level=LEVEL_CRITICAL,
            title="数据库备份失败",
            message=(
                f"备份导出未成功: {err}\n\n"
                f"这意味着当前**没有任何最新可用备份**。对存放健康检测数据的系统，"
                f"这是最高优先级的风险。\n"
                f"排查: 1) 服务器/容器是否在跑 2) SSH 免密是否配置 "
                f"3) pg_dump 用户权限。"
            ),
            context={"mode": mode, "error": err},
            dedup_key=ALERT_KEY,
        )
        return False
    log(f"导出成功 ({mode}): {out_path.name}")

    # --- 2&3. 文件校验 ---
    ok, checks, err = verify_file(out_path, cfg)
    result["steps"]["verify_file"] = {"ok": ok, "checks": checks, "error": err}
    if not ok:
        log(f"备份文件校验失败: {err}", level="ERROR")
        result["status"] = "failed"
        result["finished_at"] = datetime.now().isoformat()
        _persist(result)
        send_alert(
            level=LEVEL_CRITICAL,
            title="备份文件校验未通过",
            message=f"备份生成了，但文件不可信: {err}\n"
                    f"检查详情: {json.dumps(checks, ensure_ascii=False)}\n"
                    f"**不要把这个文件当作有效备份。**",
            context=checks,
            dedup_key=ALERT_KEY,
        )
        return False
    log(f"文件校验通过: {checks['size_bytes']} 字节压缩 / "
        f"{checks.get('uncompressed_bytes', 0)} 字节原始")

    # --- 4. 恢复验证 ---
    if cfg.get("verify_restore", True):
        r_ok, r_msg = verify_restore(out_path, cfg)
        result["steps"]["verify_restore"] = {"ok": r_ok, "message": r_msg}
        if r_ok is False:
            log(f"恢复验证失败: {r_msg}", level="ERROR")
            result["status"] = "unverified"
            result["finished_at"] = datetime.now().isoformat()
            _persist(result)
            send_alert(
                level=LEVEL_CRITICAL,
                title="备份无法恢复",
                message=f"备份文件存在且格式正确，但**实际恢复失败**: {r_msg}\n"
                        f"未经验证的备份等于没有备份。",
                context={"file": out_path.name},
                dedup_key="backup:restore_failed",
            )
            return False
        elif r_ok is None:
            log(f"恢复验证跳过: {r_msg}", level="WARN")
        else:
            log(f"恢复验证通过: {r_msg}")
            resolve_alert("backup:restore_failed")

    # --- 5. 保留策略 ---
    removed = apply_retention(backup_dir, cfg.get("retention_days", 14))
    result["steps"]["retention"] = {"removed": removed}
    if removed:
        log(f"清理过期备份 {len(removed)} 个")

    result["status"] = "success"
    result["finished_at"] = datetime.now().isoformat()
    _persist(result)
    resolve_alert(ALERT_KEY, note=f"备份已恢复正常: {out_path.name}")
    log(f"备份完成: {out_path.name}")
    log("=" * 60)
    return True


def _persist(result):
    """把备份结果写入状态，供看门狗判断「多久没有成功备份了」。"""
    try:
        state = get_state()
        state.setdefault("feedback_metrics", {})["backup"] = {
            "checked_at": result["finished_at"],
            "status": result["status"],
            "file": result.get("file"),
            "mode": result.get("mode"),
        }
        history = state.setdefault("backup_history", [])
        history.append({k: result[k] for k in ("backup_id", "started_at", "finished_at", "status")})
        state["backup_history"] = history[-30:]
        save_state(state)

        rep_dir = BASE_DIR / "reports" / "analysis"
        rep_dir.mkdir(parents=True, exist_ok=True)
        with open(rep_dir / f"{datetime.now().strftime('%Y-%m-%d')}_backup.json",
                  "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"备份结果落盘失败: {e}", level="ERROR")


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
