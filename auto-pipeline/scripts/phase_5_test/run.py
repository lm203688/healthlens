"""
阶段5：质量测试
对生成的内容进行质量检查：医疗用语扫描、Schema标记验证、链接有效性、字数检查
输出：test_report.json
"""
import sys
import json
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import start_phase, complete_phase, fail_phase, get_state, save_state, BASE_DIR, log


# 医疗风险关键词（需要特别注意的用语）
MEDICAL_RISK_TERMS = [
    ("治愈", "应避免使用'治愈'，建议用'改善'或'帮助'"),
    ("根治", "应避免使用'根治'，建议用'缓解'或'调节'"),
    ("特效", "应避免使用'特效'，建议用'可能有助于'"),
    ("包治", "严禁使用'包治'类绝对化用语"),
    ("100%", "应避免使用百分比绝对化表述"),
    ("一定有效", "应避免绝对化承诺"),
    ("药到病除", "严禁使用夸大效果的用语"),
    ("诊断", "非医疗平台不应提供诊断服务"),
    ("治疗疾病", "建议用'健康调理'或'生活方式干预'替代"),
    ("处方", "非医疗平台不应涉及处方"),
]

# Schema.org 必需字段
REQUIRED_SCHEMA_FIELDS = [
    "@context",
    "@type",
    "headline",
    "description",
    "author",
    "datePublished",
]


def check_medical_terms(content):
    """检查医疗风险用语"""
    issues = []
    for term, suggestion in MEDICAL_RISK_TERMS:
        if term in content:
            count = content.count(term)
            issues.append({
                "term": term,
                "count": count,
                "suggestion": suggestion,
                "severity": "high" if "严禁" in suggestion else "medium"
            })
    return issues


def check_schema_markup(content):
    """检查 Schema.org 结构化数据"""
    issues = []
    
    # 检查是否有 JSON-LD
    if "application/ld+json" not in content:
        issues.append({
            "field": "json_ld",
            "status": "missing",
            "message": "缺少 Schema.org JSON-LD 标记"
        })
        return issues
    
    # 提取 JSON-LD 内容
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL)
    if not match:
        issues.append({"field": "json_ld", "status": "invalid", "message": "JSON-LD 格式错误"})
        return issues
    
    try:
        data = json.loads(match.group(1).strip())
        for field in REQUIRED_SCHEMA_FIELDS:
            if field not in data:
                issues.append({
                    "field": field,
                    "status": "missing",
                    "message": f"缺少必需字段: {field}"
                })
    except json.JSONDecodeError as e:
        issues.append({"field": "json_ld", "status": "invalid", "message": f"JSON解析失败: {e}"})
    
    return issues


def check_links(content):
    """检查链接有效性（基本检查）"""
    issues = []
    # 提取所有链接
    links = re.findall(r'href=["\'](.*?)["\']', content)
    
    broken_patterns = ["#", "javascript:", "mailto:"]
    valid_links = [l for l in links if not any(l.startswith(p) for p in broken_patterns)]
    
    # 检查空链接
    empty_links = [l for l in links if l in ["", "#"]]
    if empty_links:
        issues.append({
            "type": "empty_links",
            "count": len(empty_links),
            "message": f"发现 {len(empty_links)} 个空链接"
        })
    
    return issues, len(valid_links)


def check_word_count(content, min_words=800):
    """检查字数"""
    # 简单的中文字数统计
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    english_words = len(re.findall(r'[a-zA-Z]+', content))
    total = chinese_chars + english_words
    
    if total < min_words:
        return False, total, f"字数不足: {total}/{min_words}"
    return True, total, "OK"


def check_seo_basics(content, title=""):
    """基础SEO检查"""
    issues = []
    
    # 检查 title
    if not re.search(r'<title>.+</title>', content):
        issues.append({"item": "title_tag", "status": "fail", "message": "缺少title标签"})
    
    # 检查 meta description
    if 'name="description"' not in content and "name='description'" not in content:
        issues.append({"item": "meta_description", "status": "fail", "message": "缺少meta description"})
    
    # 检查 H1
    h1_count = len(re.findall(r'<h1[ >]', content))
    if h1_count == 0:
        issues.append({"item": "h1_tag", "status": "fail", "message": "缺少H1标签"})
    elif h1_count > 1:
        issues.append({"item": "h1_tag", "status": "warning", "message": f"多个H1标签: {h1_count}个"})
    
    # 检查图片 alt
    images = re.findall(r'<img[^>]*>', content)
    no_alt = [img for img in images if 'alt=' not in img and "alt=" not in img]
    if no_alt:
        issues.append({"item": "image_alt", "status": "warning", "message": f"{len(no_alt)} 张图片缺少alt属性"})
    
    return issues


def test_content_item(item):
    """测试单个内容项"""
    content_path = BASE_DIR / item["content_file"]
    
    if not content_path.exists():
        return {
            "task_id": item["task_id"],
            "status": "failed",
            "error": f"文件不存在: {item['content_file']}",
            "checks": {}
        }
    
    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    checks = {}
    
    # 1. 医疗用语检查
    medical_issues = check_medical_terms(content)
    checks["medical_terms"] = {
        "status": "pass" if len(medical_issues) == 0 else "warning",
        "issues_found": len(medical_issues),
        "details": medical_issues[:5]  # 最多显示5个
    }
    
    # 2. Schema标记检查
    if item["type"] == "seo_knowledge_page":
        schema_issues = check_schema_markup(content)
        checks["schema_markup"] = {
            "status": "pass" if len(schema_issues) == 0 else "fail",
            "issues_found": len(schema_issues),
            "details": schema_issues
        }
    
    # 3. 链接检查
    link_issues, valid_link_count = check_links(content)
    checks["links"] = {
        "status": "pass" if len(link_issues) == 0 else "warning",
        "valid_links": valid_link_count,
        "issues": link_issues
    }
    
    # 4. 字数检查
    wc_ok, word_count, wc_msg = check_word_count(content)
    checks["word_count"] = {
        "status": "pass" if wc_ok else "fail",
        "count": word_count,
        "message": wc_msg
    }
    
    # 5. SEO基础检查
    if item["type"] == "seo_knowledge_page":
        seo_issues = check_seo_basics(content)
        checks["seo_basics"] = {
            "status": "pass" if len(seo_issues) == 0 else "warning",
            "issues_found": len(seo_issues),
            "details": seo_issues
        }
    
    # 综合判定
    all_statuses = [c["status"] for c in checks.values()]
    if "fail" in all_statuses:
        overall = "failed"
    elif "warning" in all_statuses:
        overall = "warning"
    else:
        overall = "passed"
    
    return {
        "task_id": item["task_id"],
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "status": overall,
        "checks": checks
    }


def run():
    phase = "test"
    try:
        start_phase(phase)
        
        # 校验配置可读（本阶段不消费具体配置项，保留校验以便配置写错时尽早失败）
        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            json.load(f)
        
        # 获取已生成的内容
        state = get_state()
        tasks = [t for t in state.get("development_tasks", []) if t.get("status") == "generated"]
        
        if not tasks:
            log("没有待测试的内容，跳过测试阶段")
            complete_phase(phase, output_file=None, items_processed=0)
            return True
        
        # 测试每个内容项
        results = []
        passed = 0
        failed = 0
        warnings = 0
        
        for task in tasks:
            result = test_content_item(task)
            results.append(result)
            
            if result["status"] == "passed":
                passed += 1
                # 更新任务状态
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "test_passed"
                        break
            elif result["status"] == "failed":
                failed += 1
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "test_failed"
                        break
            else:
                warnings += 1
                for t in state["development_tasks"]:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "test_warning"
                        break
        
        save_state(state)
        
        # 生成测试报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"test_{today}",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "pass_rate": f"{round(passed/len(results)*100, 1)}%" if results else "N/A"
            },
            "check_categories": {
                "medical_terms": sum(1 for r in results if r["checks"].get("medical_terms", {}).get("status") == "pass"),
                "schema_markup": sum(1 for r in results if r["checks"].get("schema_markup", {}).get("status") == "pass"),
                "word_count": sum(1 for r in results if r["checks"].get("word_count", {}).get("status") == "pass"),
            },
            "results": results,
            "failed_items": [r for r in results if r["status"] == "failed"]
        }
        
        output_file = f"reports/analysis/{today}_test_report.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(results),
            passed=passed,
            failed=failed,
            warnings=warnings
        )
        log(f"测试完成: {passed}通过, {warnings}警告, {failed}失败")
        return True
        
    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
