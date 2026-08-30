"""F线：项目运维闭环
自动检查服务器健康、安全、容器状态、医疗用语合规
输出：ops_health_report.json

修订记录 (2026-08-04) —— 本文件是 fail-open 的重灾区，修了四类问题
--------------------------------------------------------------------
1. **最严重：检查失败仍 return True**
   原逻辑无论 overall 是 healthy 还是 needs_attention 都 `return True`，
   于是 8-03 那次「端点 0/4 正常 + 数据库拒连 + SSH 超时」被 scheduler
   记录为「✅ F线 - 成功 / 全部闭环执行结束: 全部成功」。
   现在：非 healthy 一律触发告警并返回 False（退出码 1）。

2. **无告警**：发现问题只写进 JSON 文件，没有任何人会去看。
   现在接入 alerting 模块，并在恢复时发 resolved 通知。

3. **curl.exe 硬编码**：只能在 Windows 跑，迁到服务器/容器立刻全挂
   （且会被误判为「端点异常」而非「探测器坏了」）。改用 urllib，跨平台。

4. **裸 except 吞异常**：check_docker_containers 用 `except:` 吞掉一切，
   连 KeyboardInterrupt 都吃掉，且无法区分「SSH 不通」和「代码写错了」。
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from alerting import LEVEL_CRITICAL, LEVEL_WARN, resolve_alert, send_alert
from state_manager import (
    BASE_DIR,
    complete_phase,
    fail_phase,
    get_state,
    log,
    save_state,
    start_phase,
)

ALERT_KEY_ENDPOINTS = "ops:endpoints_down"
ALERT_KEY_CONTAINERS = "ops:containers_unhealthy"
ALERT_KEY_SECURITY = "ops:security_issues"


def _load_config() -> dict:
    try:
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"读取 config.json 失败: {e}", level="ERROR")
        return {}


def check_server_health(config):
    """检查服务器健康状态（跨平台实现，不依赖 curl.exe）"""
    endpoints = config.get("watchdog", {}).get("site_endpoints") or [
        "https://healthlens.cc/health",
        "https://healthlens.cc/llms.txt",
        "https://healthlens.cc/robots.txt",
        "https://healthlens.cc/sitemap.xml",
    ]
    names = {
        "/health": "API健康",
        "/llms.txt": "SEO内容",
        "/robots.txt": "Robots",
        "/sitemap.xml": "Sitemap",
    }

    checks = []
    for url in endpoints:
        name = next((v for k, v in names.items() if url.endswith(k)), url)
        started = datetime.now()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HealthLens-OpsCheck/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
            status = "ok" if 200 <= code < 300 else "error"
            checks.append({
                "name": name, "url": url, "status": status, "http_code": code,
                "latency_ms": int((datetime.now() - started).total_seconds() * 1000),
            })
        except urllib.error.HTTPError as e:
            # 服务器有响应但状态码异常——能区分「服务挂了」和「网关挂了」
            checks.append({
                "name": name, "url": url, "status": "error", "http_code": e.code,
                "error": f"HTTP {e.code}",
                "latency_ms": int((datetime.now() - started).total_seconds() * 1000),
            })
        except (urllib.error.URLError, TimeoutError) as e:
            checks.append({
                "name": name, "url": url, "status": "error", "http_code": 0,
                "error": f"连接失败: {str(e)[:120]}",
            })
        except Exception as e:
            # 探测器本身出错，与「端点异常」区分开，避免误判
            checks.append({
                "name": name, "url": url, "status": "probe_error", "http_code": -1,
                "error": f"探测器异常: {str(e)[:120]}",
            })
    return checks


def check_site_identity(config):
    """身份校验：确认站点返回的确实是 HealthLens 自己的内容。

    背景（2026-08-04 事故）：config.json 里的 ssh_host 指向 150.158.119.19，
    但那台机器上跑的是 AIShield。带 Host 头直连源站会拿到 200 + AIShield 首页。
    只看 HTTP 状态码的探测器会认为「一切正常」。
    因此必须做内容级身份校验：既要出现自己的标识，也不能出现别的项目的标识。
    """
    wd = config.get("watchdog", {})
    base = (config.get("project_url") or "https://healthlens.cc").rstrip("/")
    expect = wd.get("identity_markers") or ["healthlens", "HealthLens"]
    forbid = wd.get("forbidden_markers") or ["aishield", "AIShield", "roboparts", "oraclemind"]

    findings = []
    for path in wd.get("identity_paths") or ["/", "/robots.txt"]:
        url = base + path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HealthLens-OpsCheck/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if not (200 <= resp.status < 300):
                    findings.append({"path": path, "status": "unreachable",
                                     "detail": f"HTTP {resp.status}，无法校验身份"})
                    continue
                body = resp.read(60000).decode("utf-8", errors="ignore")
        except Exception as e:
            findings.append({"path": path, "status": "unreachable",
                             "detail": f"无法获取内容: {str(e)[:100]}"})
            continue

        low = body.lower()
        hit_forbidden = [m for m in forbid if m.lower() in low]
        hit_expected = [m for m in expect if m.lower() in low]

        if hit_forbidden:
            findings.append({
                "path": path, "status": "wrong_site",
                "detail": f"页面中出现了其他项目的标识 {hit_forbidden}，"
                          f"说明该域名/源站正在提供别的项目的内容。",
            })
        elif not hit_expected:
            findings.append({
                "path": path, "status": "unrecognized",
                "detail": f"页面中找不到任何 HealthLens 标识（期望包含 {expect} 之一），"
                          f"可能是默认页/占位页/被替换。",
            })
        else:
            findings.append({"path": path, "status": "ok",
                             "detail": f"身份标识匹配: {hit_expected[:2]}"})
    return findings


def check_deploy_target(config):
    """部署目标合理性校验：防止「配置指向别人的服务器」这类静默错误。"""
    issues = []
    dep = config.get("deployment", {})
    host = dep.get("ssh_host") or ""
    if not host or "<" in host or "TODO" in host.upper():
        issues.append({"level": "critical", "item": "部署目标未配置",
                       "detail": f"deployment.ssh_host = {host!r}，无法执行任何真实部署。"})
        return issues

    known_foreign = config.get("deployment", {}).get("known_foreign_hosts") or {}
    ip = host.split("@")[-1]
    if ip in known_foreign:
        issues.append({
            "level": "critical", "item": "部署目标指向其他项目的服务器",
            "detail": f"ssh_host={host} 属于「{known_foreign[ip]}」项目。"
                      f"向该机器部署会污染其他项目，必须先修正为 HealthLens 自己的服务器。",
        })

    if dep.get("verified_at") is None:
        issues.append({"level": "warn", "item": "部署目标从未验证",
                       "detail": "deployment.verified_at 为空，说明这个部署地址从未成功连通过。"})
    return issues


def check_security():
    """安全检查"""
    issues = []
    gitignore_path = BASE_DIR.parent / "healthlens" / ".gitignore"
    if gitignore_path.exists():
        try:
            with open(gitignore_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if ".env" not in content:
                issues.append({"severity": "critical", "issue": ".env 未在 .gitignore 中"})
        except Exception as e:
            issues.append({"severity": "warning", "issue": f".gitignore 读取失败: {e}"})
    else:
        issues.append({"severity": "warning", "issue": ".gitignore 不存在"})

    # 检查 .env 是否被 git 跟踪（比检查 .gitignore 更直接）
    healthlens_dir = BASE_DIR.parent / "healthlens"
    if (healthlens_dir / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "ls-files", "--error-unmatch", ".env"],
                cwd=str(healthlens_dir), capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                issues.append({"severity": "critical", "issue": ".env 已被 git 跟踪，存在凭证泄露风险"})
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass  # git 不可用不算安全问题
    return issues


def check_docker_containers(config):
    """检查 Docker 容器状态（通过 SSH 或本机 docker）

    注意：SSH 不通 ≠ 容器不健康。必须区分，否则会把「看不见」
    误报成「它坏了」，或反过来把真故障当成网络抖动忽略掉。
    """
    ssh_host = config.get("backup", {}).get("ssh_host", "")
    if not ssh_host:
        return {
            "reachable": False,
            "reason": "未配置 ssh_host，无法远程检查容器状态",
            "containers": [],
        }
    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=10", ssh_host,
             "docker ps --format '{{.Names}}|{{.Status}}'"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return {
                "reachable": False,
                "reason": f"SSH 失败 (exit {result.returncode}): {result.stderr.strip()[:150]}",
                "containers": [],
            }
        containers = []
        for line in result.stdout.strip().splitlines():
            if "|" in line:
                name, status = line.split("|", 1)
                containers.append({"name": name.strip(), "status": status.strip()})
        return {"reachable": True, "reason": "", "containers": containers}
    except subprocess.TimeoutExpired:
        return {"reachable": False, "reason": "SSH 超时(20s)", "containers": []}
    except FileNotFoundError:
        return {"reachable": False, "reason": "本机未安装 ssh 客户端", "containers": []}
    except Exception as e:
        return {"reachable": False, "reason": f"SSH 异常: {str(e)[:150]}", "containers": []}


def check_medical_terms():
    """扫描前端代码中的高风险医疗用语（合规护栏）。

    覆盖两处，消除监控盲区：
      1. 当前活跃前端 frontend/src/（Vite + React，真正面向用户的代码）。
         此前仅扫描历史文件，导致这部分从未被检查。
      2. 历史前端 healthlens/frontend/index.html（若仍在线上则继续监控）。
    """
    risky_terms = ["治愈", "根治", "特效", "诊断", "处方"]
    # 免责/否定语境：如"不提供医疗诊断、治疗或处方服务"是合规必需要件，
    # 若一并报警会形成噪音，长期将淹没真实风险（"狼来了"效应）。
    negation_cues = [
        "不提供", "不构成", "不是", "并非", "不能", "无法", "非医疗",
        "免责", "不作为", "不具备", "请勿", "不得", "不应", "不可",
        # 以下为站内实际使用的去医疗化表述，缺一即产生大量误报
        "不替代", "而非", "不能下", "零处方", "0 处方", "避免", "排除",
    ]
    window = 40

    findings = []

    def _scan_file(path: Path, label: str, tier: str) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log(f"医疗用语扫描失败 {label}: {e}", level="WARN")
            return
        for term in risky_terms:
            risk_hits = 0
            total = 0
            start = 0
            while True:
                idx = content.find(term, start)
                if idx == -1:
                    break
                total += 1
                start = idx + len(term)

                # 排除合法复合词："处方药"是标准医药名词，提及并不违规
                if content[idx:idx + len(term) + 1] == f"{term}药":
                    continue

                ctx = content[max(0, idx - window): idx + len(term) + window]
                # 排除批判性引用（如 ❌ "基因检测=定制处方" 实为否定该说法）
                critique_marks = ["❌", "✗", "✘", "错误", "误区", "伪"]
                # 出现在免责/否定语境中属合规要件，不计为风险
                if any(cue in ctx for cue in negation_cues):
                    continue
                if any(mark in ctx for mark in critique_marks):
                    continue

                risk_hits += 1

            if risk_hits:
                findings.append({
                    "term": term,
                    "file": label,
                    "count": risk_hits,
                    "total_occurrences": total,
                    # online=线上产物（最高优先级）source=活跃源码 legacy=历史文件
                    "tier": tier,
                    "is_active_frontend": label.startswith("frontend/src/"),
                })

    def _scan_tree(root: Path, label_prefix: str, pattern: str, tier: str) -> None:
        if not root.exists():
            return
        for path in sorted(root.rglob(pattern)):
            _scan_file(path, f"{label_prefix}/{path.relative_to(root).as_posix()}", tier)

    # 优先级 1：线上产物 auto-pipeline/dist/（CF Pages 实际托管，真正面向用户）。
    # 此前完全未扫描，是最大的监控盲区。
    _scan_tree(BASE_DIR / "dist", "auto-pipeline/dist", "*.html", "online")

    # 优先级 2：当前活跃前端源码 frontend/src/
    _scan_tree(BASE_DIR.parent / "frontend" / "src", "frontend/src", "*.jsx", "source")
    _scan_tree(BASE_DIR.parent / "frontend" / "src", "frontend/src", "*.js", "source")

    # 优先级 3：历史前端文件（多为死代码，保留以感知遗留风险）
    legacy_path = BASE_DIR.parent / "healthlens" / "frontend" / "index.html"
    if legacy_path.exists():
        _scan_file(legacy_path, "healthlens/frontend/index.html", "legacy")

    return findings


def _evaluate_and_alert(health_checks, containers_info, security_issues, medical_findings,
                        identity_findings=None, deploy_issues=None):
    """判定整体健康度并发出/解除告警。

    返回 (overall, is_ok)。is_ok 决定进程退出码——这是 fail-loud 的关键：
    退出码必须真实反映系统状态，否则上游调度器只会继续说「全部成功」。
    """
    total = len(health_checks)
    ok_count = sum(1 for c in health_checks if c["status"] == "ok")
    error_count = sum(1 for c in health_checks if c["status"] == "error")
    probe_errors = [c for c in health_checks if c["status"] == "probe_error"]

    unhealthy_containers = [
        c for c in containers_info["containers"]
        if "unhealthy" in c.get("status", "").lower()
        or "restarting" in c.get("status", "").lower()
        or "exited" in c.get("status", "").lower()
    ]
    critical_security = [s for s in security_issues if s.get("severity") == "critical"]

    # ---- 端点告警 ----
    if error_count > 0:
        level = LEVEL_CRITICAL if ok_count == 0 else LEVEL_WARN
        down = [f"{c['name']}({c.get('http_code')})" for c in health_checks if c["status"] == "error"]
        send_alert(
            level=level,
            title=f"站点端点异常 {error_count}/{total}",
            message=(
                f"以下端点探测失败: {', '.join(down)}。\n"
                f"{'全部端点不可用，站点可视为完全宕机。' if ok_count == 0 else '部分端点不可用。'}\n"
                f"建议排查顺序: 1) 容器是否在跑 2) alembic 迁移是否成功 "
                f"3) 反向代理/CDN 回源配置 4) 服务器磁盘与内存。"
            ),
            context={"checks": health_checks},
            dedup_key=ALERT_KEY_ENDPOINTS,
        )
    else:
        resolve_alert(ALERT_KEY_ENDPOINTS, note=f"全部 {total} 个端点已恢复正常。")

    # ---- 探测器自身故障（不同于端点故障，必须单独提示）----
    if probe_errors:
        send_alert(
            level=LEVEL_WARN,
            title="健康探测器自身异常",
            message=f"{len(probe_errors)} 个端点的探测过程报错，本轮结果不可信: "
                    f"{[p.get('error') for p in probe_errors]}",
            context={"probe_errors": probe_errors},
            dedup_key="ops:probe_error",
        )

    # ---- 容器告警 ----
    if not containers_info["reachable"]:
        send_alert(
            level=LEVEL_WARN,
            title="无法连接服务器查看容器状态",
            message=(
                f"原因: {containers_info['reason']}。\n"
                f"注意：这意味着容器状态未知，不等于容器正常。"
                f"若同时出现端点异常，应优先按「服务器不可达」处理。"
            ),
            context={"reason": containers_info["reason"]},
            dedup_key="ops:ssh_unreachable",
        )
    else:
        resolve_alert("ops:ssh_unreachable")
        if unhealthy_containers:
            send_alert(
                level=LEVEL_CRITICAL,
                title=f"{len(unhealthy_containers)} 个容器异常",
                message="异常容器: " + ", ".join(
                    f"{c['name']}({c['status']})" for c in unhealthy_containers),
                context={"containers": unhealthy_containers},
                dedup_key=ALERT_KEY_CONTAINERS,
            )
        else:
            resolve_alert(ALERT_KEY_CONTAINERS)

    # ---- 身份校验告警（防「200 但是别人的站」）----
    identity_findings = identity_findings or []
    wrong_site = [f for f in identity_findings if f["status"] in ("wrong_site", "unrecognized")]
    if wrong_site:
        send_alert(
            level=LEVEL_CRITICAL,
            title="站点身份校验失败——返回的不是 HealthLens 的内容",
            message=(
                "\n".join(f"{f['path']}: {f['detail']}" for f in wrong_site) +
                "\n\n这比宕机更危险：端点可能返回 200，让所有只看状态码的监控误判为正常。"
                "\n排查: 1) DNS/CDN 回源是否指向了正确的服务器 "
                "2) nginx 是否缺少本域名的 server_name 配置而落到了默认站 "
                "3) 是否被其他项目覆盖部署。"
            ),
            context={"identity": identity_findings},
            dedup_key="ops:wrong_site_identity",
        )
    elif identity_findings and all(f["status"] == "ok" for f in identity_findings):
        resolve_alert("ops:wrong_site_identity", note="站点身份校验已恢复正常。")

    # ---- 部署目标合理性告警 ----
    deploy_issues = deploy_issues or []
    critical_deploy = [d for d in deploy_issues if d["level"] == "critical"]
    if critical_deploy:
        send_alert(
            level=LEVEL_CRITICAL,
            title="部署目标配置有误",
            message="\n".join(f"[{d['item']}] {d['detail']}" for d in critical_deploy),
            context={"deploy_issues": deploy_issues},
            dedup_key="ops:bad_deploy_target",
        )
    else:
        resolve_alert("ops:bad_deploy_target")

    # ---- 安全告警 ----
    if critical_security:
        send_alert(
            level=LEVEL_CRITICAL,
            title=f"{len(critical_security)} 项严重安全问题",
            message="\n".join(s["issue"] for s in critical_security),
            context={"issues": critical_security},
            dedup_key=ALERT_KEY_SECURITY,
        )
    else:
        resolve_alert(ALERT_KEY_SECURITY)

    # ---- 综合判定 ----
    problems = []
    if error_count:
        problems.append(f"端点异常×{error_count}")
    if not containers_info["reachable"]:
        problems.append("服务器不可达")
    if unhealthy_containers:
        problems.append(f"容器异常×{len(unhealthy_containers)}")
    if critical_security:
        problems.append(f"安全问题×{len(critical_security)}")
    if medical_findings:
        problems.append(f"医疗用语×{len(medical_findings)}")
    if wrong_site:
        problems.append(f"站点身份错误×{len(wrong_site)}")
    if critical_deploy:
        problems.append(f"部署目标错误×{len(critical_deploy)}")

    if not problems:
        return "healthy", True, ok_count, error_count, unhealthy_containers
    # 端点全挂 / 严重安全问题 / 身份错误 / 部署目标错误 → down；其余 → needs_attention
    overall = "down" if (ok_count == 0 or critical_security or unhealthy_containers
                         or wrong_site or critical_deploy) else "needs_attention"
    log(f"运维检查判定 {overall}: {'; '.join(problems)}", level="ERROR")
    return overall, False, ok_count, error_count, unhealthy_containers


def run():
    phase = "ops_health_f"
    try:
        start_phase(phase)
        config = _load_config()

        health_checks = check_server_health(config)
        security_issues = check_security()
        containers_info = check_docker_containers(config)
        medical_findings = check_medical_terms()
        identity_findings = check_site_identity(config)
        deploy_issues = check_deploy_target(config)

        overall, is_ok, ok_count, error_count, unhealthy_containers = _evaluate_and_alert(
            health_checks, containers_info, security_issues, medical_findings,
            identity_findings, deploy_issues
        )

        state = get_state()
        state.setdefault("feedback_metrics", {})["ops_health"] = {
            "checked_at": datetime.now().isoformat(),
            "overall": overall,
            "endpoints_ok": ok_count,
            "endpoints_error": error_count,
            "server_reachable": containers_info["reachable"],
            "containers_unhealthy": len(unhealthy_containers),
            "security_issues": len(security_issues),
            "medical_terms_found": len(medical_findings),
        }
        save_state(state)

        report = {
            "report_id": f"ops_f_{datetime.now().strftime('%Y%m%d')}",
            "generated_at": datetime.now().isoformat(),
            "overall_status": overall,
            "endpoint_checks": health_checks,
            "server_reachable": containers_info["reachable"],
            "server_unreachable_reason": containers_info["reason"],
            "containers": containers_info["containers"],
            "security_issues": security_issues,
            "medical_terms": medical_findings,
            "site_identity": identity_findings,
            "deploy_target_issues": deploy_issues,
            "actions_needed": (
                [] if is_ok else (
                    [{"action": f"修复端点: {c['name']} ({c.get('http_code', 'N/A')})", "severity": "critical"}
                     for c in health_checks if c["status"] == "error"] +
                    ([{"action": f"恢复服务器连通性: {containers_info['reason']}", "severity": "high"}]
                     if not containers_info["reachable"] else []) +
                    [{"action": f"修复容器: {c['name']} ({c['status']})", "severity": "critical"}
                     for c in unhealthy_containers] +
                    [{"action": f"站点身份: {f['path']} — {f['detail'][:80]}", "severity": "critical"}
                     for f in identity_findings if f["status"] in ("wrong_site", "unrecognized")] +
                    [{"action": f"部署目标: {d['item']} — {d['detail'][:80]}", "severity": d["level"]}
                     for d in deploy_issues] +
                    [{"action": f"安全: {s['issue']}", "severity": s["severity"]} for s in security_issues] +
                    [{"action": f"医疗用语: 替换'{m['term']}'({m.get('count', 1)}处)", "severity": "medium"}
                     for m in medical_findings]
                )
            ),
        }

        output_file = f"reports/analysis/{datetime.now().strftime('%Y-%m-%d')}_ops_health_f.json"
        output_path = BASE_DIR / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        if is_ok:
            complete_phase(phase, output_file=output_file,
                           items_processed=len(health_checks) + len(containers_info["containers"]))
            log(f"F线运维检查完成: 端点 {ok_count}/{len(health_checks)} 正常, 总体 {overall}")
        else:
            # 关键改动：检查发现问题时标记为 failed，不再伪装成 completed
            fail_phase(phase, f"运维检查未通过: {overall} (端点 {ok_count}/{len(health_checks)} 正常)")
            log(f"F线运维检查未通过: 端点 {ok_count}/{len(health_checks)} 正常, 总体 {overall}", level="ERROR")

        return is_ok

    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        send_alert(
            level=LEVEL_CRITICAL,
            title="F线运维检查脚本崩溃",
            message=f"运维检查本身出错，系统健康状态未知: {str(e)[:300]}",
            context={"traceback": traceback.format_exc()[-800:]},
            dedup_key="ops:script_crash",
        )
        return False


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
