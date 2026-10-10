"""HealthLens 公共健康工具路由

提供4个免费交互式健康计算器页面，用于 SEO 驱动的用户获取。
每个工具是自包含的交互式 HTML 页面，包含 JavaScript 计算逻辑、
Schema.org 结构化数据和浮动 CTA 按钮。

挂载路径: /tools/

工具列表:
  1. GET  /tools/bmi-calculator           — BMI 计算器
     POST /tools/bmi-calculator/calculate  — BMI 计算器 API
  2. GET  /tools/sleep-score-calculator           — 睡眠质量评分器
     POST /tools/sleep-score-calculator/calculate  — 睡眠评分 API
  3. GET  /tools/tcm-constitution-test           — 中医体质自测
     POST /tools/tcm-constitution-test/calculate — 体质自测 API
  4. GET  /tools/food-medicine-query           — 药食同源食材查询
     POST /tools/food-medicine-query/search     — 食材查询 API
"""

import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.services.seo_factory import FOOD_MEDICINE_HOMOLOGY


# ============================================================================
# 路由器
# ============================================================================

tools_public_router = APIRouter(prefix="/tools", tags=["public-tools"])

SITE_NAME = "HealthLens"
BASE_URL = "https://healthlens.com"


# ============================================================================
# 公共样式和组件
# ============================================================================

_BASE_CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--primary:#0d8a6a;--primary-dark:#09705a;--primary-light:#e6f5f0;
--bg:#FDFBF7;--bg2:#F0F2EC;--ink:#2C3E2D;--muted:#6B7B6C;--rule:#D5DCD6;
--accent:#0d8a6a;--accent2:#D4A843;--radius:10px;
--gradient:#11998e;--gradient-end:#38ef7d}
body{font-family:'PingFang SC','Microsoft YaHei',-apple-system,sans-serif;
font-size:16px;line-height:1.8;color:var(--ink);background:var(--bg);
-webkit-font-smoothing:antialiased}
.container{max-width:780px;margin:0 auto;padding:2rem 1.5rem}
.breadcrumb{font-size:.82rem;color:var(--muted);margin-bottom:1.2rem}
.breadcrumb a{color:var(--accent);text-decoration:none}
.breadcrumb a:hover{text-decoration:underline}
.breadcrumb .sep{margin:0 .4rem}
.breadcrumb .current{color:var(--ink)}
header.tool-header{background:linear-gradient(135deg,var(--gradient),var(--gradient-end));
color:#fff;padding:3rem 1.5rem;text-align:center;margin:-2rem -1.5rem 2rem;border-radius:var(--radius)}
header.tool-header h1{font-size:1.8rem;font-weight:700;margin-bottom:.4rem;text-shadow:0 1px 4px rgba(0,0,0,.1)}
header.tool-header p{opacity:.92;font-size:1rem;max-width:500px;margin:0 auto}
.card{background:#fff;border-radius:var(--radius);padding:1.5rem;box-shadow:0 2px 12px rgba(13,138,106,.06);margin-bottom:1.25rem}
.card h2{font-size:1.15rem;color:var(--ink);margin-bottom:.75rem;padding-left:.6rem;border-left:3px solid var(--accent)}
.card label{display:block;font-size:.88rem;font-weight:600;color:var(--ink);margin-bottom:.35rem}
.card input[type=number],.card select{width:100%;padding:.6rem .8rem;
border:1.5px solid var(--rule);border-radius:6px;font-size:.92rem;
transition:border-color .2s;background:#fff;color:var(--ink)}
.card input:focus,.card select:focus{outline:none;border-color:var(--accent)}
.card .form-row{display:flex;gap:1rem;margin-bottom:1rem}
.card .form-row>div{flex:1}
.card .form-group{margin-bottom:1rem}
.card .form-group input{width:100%}
.btn-calc{display:block;width:100%;padding:.75rem 0;background:linear-gradient(135deg,var(--gradient),var(--gradient-end));
color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:700;cursor:pointer;
transition:transform .15s,box-shadow .15s;box-shadow:0 3px 12px rgba(17,153,142,.3)}
.btn-calc:hover{transform:translateY(-1px);box-shadow:0 5px 18px rgba(17,153,142,.4)}
.btn-calc:active{transform:translateY(0)}
.result-box{background:var(--primary-light);border-radius:var(--radius);padding:1.5rem;margin-top:1.25rem;text-align:center;display:none}
.result-box.visible{display:block;animation:fadeUp .4s ease}
.result-box .score-big{font-size:2.8rem;font-weight:800;color:var(--primary);line-height:1.2}
.result-box .category{font-size:1.1rem;font-weight:600;margin:.3rem 0 .6rem;padding:.2rem .8rem;
display:inline-block;border-radius:20px;background:#fff;color:var(--primary)}
.result-box .detail{font-size:.88rem;color:var(--muted);line-height:1.7;text-align:left;margin-top:.75rem}
.result-box .advice{background:#fff;border-radius:8px;padding:1rem;margin-top:.75rem;font-size:.88rem;
text-align:left;color:var(--ink);border-left:3px solid var(--accent)}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
/* Floating CTA */
.cta-float{position:fixed;bottom:24px;right:24px;z-index:9999}
.cta-float-btn{display:flex;align-items:center;gap:6px;background:linear-gradient(135deg,var(--gradient),var(--gradient-end));
color:#fff;padding:12px 22px;border-radius:50px;text-decoration:none;font-weight:600;font-size:.88rem;
box-shadow:0 4px 20px rgba(17,153,142,.45);transition:transform .2s,box-shadow .2s;
white-space:nowrap;max-width:280px}
.cta-float-btn:hover{transform:translateY(-2px) scale(1.02);box-shadow:0 6px 28px rgba(17,153,142,.55)}
.cta-float-btn .points{background:rgba(255,255,255,.25);padding:2px 8px;border-radius:12px;font-size:.76rem}
/* FAQ */
.faq-section{margin-top:2rem;padding-top:1.5rem;border-top:1px solid var(--rule)}
.faq-section h2{text-align:center;border-left:none;padding-left:0;margin-bottom:1rem}
.faq-item{margin-bottom:1rem;padding:1rem;background:var(--bg2);border-radius:var(--radius)}
.faq-item h3{font-size:.92rem;color:var(--ink);margin-bottom:.3rem}
.faq-item p{font-size:.86rem;color:var(--muted);margin:0}
/* TCM test */
.constitution-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-top:.5rem}
.constitution-bar-wrap{margin-bottom:.75rem}
.constitution-bar-label{display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:.2rem}
.constitution-bar-label span:last-child{font-weight:700;color:var(--primary)}
.constitution-bar{height:8px;background:var(--bg2);border-radius:4px;overflow:hidden}
.constitution-bar-fill{height:100%;border-radius:4px;transition:width .6s ease}
/* Food cards */
.food-card{border:1.5px solid var(--rule);border-radius:var(--radius);padding:1.25rem;margin-bottom:1rem;
transition:border-color .2s,box-shadow .2s}
.food-card:hover{border-color:var(--accent);box-shadow:0 2px 12px rgba(13,138,106,.1)}
.food-card h3{color:var(--primary);font-size:1.05rem;margin-bottom:.4rem}
.food-card .meta{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:.6rem}
.food-card .tag{background:var(--primary-light);color:var(--primary);padding:.15rem .6rem;border-radius:12px;font-size:.78rem;font-weight:600}
.food-card .effect{font-size:.9rem;color:var(--ink)}
.food-card .usage{font-size:.84rem;color:var(--muted);margin-top:.5rem;border-top:1px dashed var(--rule);padding-top:.5rem}
.food-card a{color:var(--accent);text-decoration:none;font-size:.84rem}
.food-card a:hover{text-decoration:underline}
footer{text-align:center;padding-top:1.5rem;border-top:1px solid var(--rule);font-size:.78rem;color:var(--muted);margin-top:2rem}
footer a{color:var(--accent);text-decoration:none}
/* Search */
.search-wrap{display:flex;gap:.6rem;margin-bottom:1rem}
.search-wrap input{flex:1}
.search-wrap select{padding:.6rem;border:1.5px solid var(--rule);border-radius:6px;font-size:.88rem;background:#fff}
.search-results{margin-top:1rem}
.no-result{text-align:center;padding:2rem;color:var(--muted);font-size:.9rem}
/* Slider */
input[type=range]{-webkit-appearance:none;width:100%;height:6px;background:var(--bg2);border-radius:3px;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;background:var(--primary);
border-radius:50%;cursor:pointer;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.15)}
.slider-value{display:inline-block;min-width:2.5em;text-align:center;font-weight:700;color:var(--primary)}
.radio-group{display:flex;gap:.8rem;flex-wrap:wrap;margin-top:.25rem}
.radio-group label{display:flex;align-items:center;gap:.3rem;font-weight:400;cursor:pointer;font-size:.88rem}
.radio-group input[type=radio]{margin:0}
/* Limitation */
.disclaimer{background:#FFF8E8;border-left:4px solid var(--accent2);padding:1rem 1.25rem;
border-radius:0 var(--radius) var(--radius) 0;margin-top:1.5rem;font-size:.82rem;color:#8A7A4A}
.disclaimer strong{color:#6B5A2A}
@media(max-width:600px){.container{padding:1.25rem 1rem}header.tool-header{padding:2rem 1rem;margin:-1.25rem -1rem 1.5rem}
header.tool-header h1{font-size:1.4rem}.form-row{flex-direction:column;gap:0}.constitution-grid{grid-template-columns:1fr}
.cta-float-btn{font-size:.8rem;padding:10px 16px;max-width:220px}.cta-float{bottom:16px;right:16px}}"""

_FOOTER_HTML = f"""<footer>
<p>{SITE_NAME} 免费健康工具 · 以上内容仅供健康教育和日常保健参考，不构成任何医学诊断或治疗方案。</p>
<p><a href="{BASE_URL}/register">免费注册</a> · <a href="{BASE_URL}">回到首页</a></p>
</footer>"""

_BREADCRUMB_HTML = f"""<nav class="breadcrumb" aria-label="Breadcrumb">
<a href="{BASE_URL}">首页</a><span class="sep">/</span>
<a href="{BASE_URL}/health-tools/">健康工具</a><span class="sep">/</span>
<span class="current">{{tool_name}}</span>
</nav>"""

_DISCLAIMER_HTML = """<div class="disclaimer">
<p><strong>内容说明：</strong>本工具计算结果仅供健康教育和日常保健参考，不构成医学诊断或治疗方案建议。
个体差异较大，具体调理方案请在专业健康管理顾问指导下制定。如有不适请及时就医。</p>
</div>"""


def _make_page_html(
    title: str,
    meta_desc: str,
    meta_keywords: str,
    canonical_url: str,
    tool_name: str,
    schema_json_list: list[dict],
    faq_items: list[dict],
    cta_text: str,
    cta_points: str,
    body_html: str,
    extra_head: str = "",
) -> str:
    """组装完整的工具页面 HTML"""
    # JSON-LD
    schema_scripts = ""
    for s in schema_json_list:
        schema_scripts += f'<script type="application/ld+json">\n{json.dumps(s, ensure_ascii=False, indent=2)}\n</script>\n'

    # FAQ HTML
    faq_html = ""
    if faq_items:
        faq_html = '<section class="faq-section"><h2>常见疑问</h2>'
        for q in faq_items:
            faq_html += f'<div class="faq-item"><h3>{q["question"]}</h3><p>{q["answer"]}</p></div>'
        faq_html += '</section>'

    breadcrumb = _BREADCRUMB_HTML.format(tool_name=tool_name)
    cta_btn = f'<a href="{BASE_URL}/register" class="cta-float-btn">{cta_text}<span class="points">{cta_points}</span></a>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - {SITE_NAME}</title>
<meta name="description" content="{meta_desc}">
<meta name="keywords" content="{meta_keywords}">
<meta name="robots" content="index, follow">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical_url}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="zh_CN">
<link rel="canonical" href="{canonical_url}">
{schema_scripts}
{extra_head}
<style>{_BASE_CSS}</style>
</head>
<body>
<div class="container">
{breadcrumb}
<header class="tool-header">
<h1>{tool_name}</h1>
<p>{SITE_NAME} · 免费 AI 健康管理平台</p>
</header>
{body_html}
{_DISCLAIMER_HTML}
{faq_html}
{_FOOTER_HTML}
</div>
<div class="cta-float">{cta_btn}</div>
</body>
</html>"""
    return html


# ============================================================================
# 1. BMI 计算器
# ============================================================================

# POST 请求模型
class BMICalculateRequest(BaseModel):
    height: float = Field(..., ge=50, le=250, description="身高(cm)")
    weight: float = Field(..., ge=10, le=500, description="体重(kg)")
    age: int = Field(..., ge=1, le=150, description="年龄")
    gender: str = Field(..., pattern="^(male|female)$", description="性别: male/female")


def _bmi_result(height: float, weight: float, age: int, gender: str) -> dict:
    """计算 BMI 并返回完整结果"""
    h_m = height / 100
    bmi = round(weight / (h_m * h_m), 1)

    if bmi < 18.5:
        category = "偏瘦"
        cat_color = "#3b82f6"
        risk = "低体重可能导致营养不良、免疫力下降、骨质疏松等问题"
    elif bmi < 24:
        category = "正常"
        cat_color = "#22c55e"
        risk = "体重在健康范围内，继续保持良好的生活习惯"
    elif bmi < 28:
        category = "超重"
        cat_color = "#f59e0b"
        risk = "超重会增加心血管疾病、2型糖尿病等慢性病的风险"
    else:
        category = "肥胖"
        cat_color = "#ef4444"
        risk = "肥胖显著增加高血压、糖尿病、脂肪肝等多种慢性病风险"

    # 个性化建议
    if bmi < 18.5:
        advice = (
            "建议适当增加优质蛋白摄入（如鸡蛋、鱼虾、瘦肉、豆制品），"
            "搭配山药、红枣等健脾益气食材进行日常食养调理。"
            "建议每周进行3-4次中等强度运动，配合充足的睡眠。"
        )
    elif bmi < 24:
        advice = (
            "当前体重在健康范围内。建议继续保持均衡饮食和规律运动。"
            "可关注药食同源食材的日常保健搭配，如枸杞代茶饮、百合莲子粥等。"
        )
    elif bmi < 28:
        advice = (
            "建议控制高糖高脂饮食，增加膳食纤维摄入（如薏苡仁、荷叶、山楂等）。"
            "推荐每周进行150分钟以上中等强度有氧运动。"
            "可尝试药食同源方案辅助调理代谢功能。"
        )
    else:
        advice = (
            "建议在专业健康管理顾问指导下制定综合调理方案。"
            "饮食上可选用荷叶、山楂、决明子等辅助食材。"
            "运动应循序渐进，避免剧烈运动。建议先进行体质评估以获取个性化方案。"
        )

    # 理想体重范围
    ideal_low = round(18.5 * h_m * h_m, 1)
    ideal_high = round(23.9 * h_m * h_m, 1)

    return {
        "bmi": bmi,
        "category": category,
        "cat_color": cat_color,
        "risk": risk,
        "advice": advice,
        "ideal_weight_range": f"{ideal_low} - {ideal_high} kg",
        "health_risk_level": "低" if 18.5 <= bmi < 24 else ("中等" if bmi < 28 else "较高"),
    }


_BMI_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "BMI计算器",
    "description": "免费的在线BMI计算器，输入身高体重即可获取体质指数和健康风险分析",
    "url": f"{BASE_URL}/tools/bmi-calculator",
    "applicationCategory": "HealthApplication",
    "operatingSystem": "Web",
    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
    "author": {"@type": "Organization", "name": SITE_NAME},
    "inLanguage": "zh-CN",
}

_BMI_FAQ_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "BMI 是什么？怎么计算？",
            "acceptedAnswer": {"@type": "Answer", "text": "BMI（体质指数）是国际上常用的衡量人体胖瘦程度的标准。计算公式为体重(kg)除以身高(m)的平方。例如身高170cm、体重65kg的人，BMI = 65 / (1.7 x 1.7) = 22.5。"},
        },
        {
            "@type": "Question",
            "name": "中国人的 BMI 正常范围是多少？",
            "acceptedAnswer": {"@type": "Answer", "text": "中国成人的 BMI 标准与世界卫生组织有所不同。中国标准为：偏瘦 < 18.5，正常 18.5-23.9，超重 24-27.9，肥胖 >= 28。本计算器已采用中国标准。"},
        },
        {
            "@type": "Question",
            "name": "BMI 有什么局限性？",
            "acceptedAnswer": {"@type": "Answer", "text": "BMI 不能区分肌肉和脂肪的比例，健身人群可能 BMI 偏高但实际体脂率正常。BMI 也不适用于孕妇、儿童和老年人。建议结合体脂率和腰围综合评估。"},
        },
        {
            "@type": "Question",
            "name": "如何科学地控制体重？",
            "acceptedAnswer": {"@type": "Answer", "text": "科学控制体重需要综合饮食管理、规律运动和充足睡眠。建议通过体质评估了解自身特点，制定个性化的食养调理方案。避免极端节食，追求可持续的健康管理方式。"},
        },
    ],
}


def _build_bmi_page() -> str:
    """构建 BMI 计算器完整 HTML 页面"""
    title = "免费BMI计算器 - 在线体质指数计算"
    meta_desc = "免费在线BMI计算器，输入身高体重秒算体质指数。采用中国成人BMI标准，提供健康风险分析和个性化食养调理建议。"
    meta_keywords = "BMI计算器,BMI计算,体质指数,体重指数,身高体重计算,健康自测,免费BMI工具,中国BMI标准"
    canonical = f"{BASE_URL}/tools/bmi-calculator"

    body = f"""<div class="card">
<h2>输入你的身体数据</h2>
<div class="form-row">
<div class="form-group"><label>身高（厘米）</label><input type="number" id="bmi-height" placeholder="例如：170" min="50" max="250" step="1"></div>
<div class="form-group"><label>体重（千克）</label><input type="number" id="bmi-weight" placeholder="例如：65" min="10" max="500" step="0.1"></div>
</div>
<div class="form-row">
<div class="form-group"><label>年龄</label><input type="number" id="bmi-age" placeholder="例如：30" min="1" max="150" step="1"></div>
<div class="form-group"><label>性别</label><select id="bmi-gender"><option value="male">男</option><option value="female">女</option></select></div>
</div>
<button class="btn-calc" onclick="calcBMI()">计算我的 BMI</button>
<div class="result-box" id="bmi-result">
<div class="score-big" id="bmi-value"></div>
<div class="category" id="bmi-category"></div>
<div class="detail" id="bmi-detail"></div>
<div class="advice" id="bmi-advice"></div>
</div>
</div>
<script>
function calcBMI(){{var h=parseFloat(document.getElementById('bmi-height').value),
w=parseFloat(document.getElementById('bmi-weight').value),
a=parseInt(document.getElementById('bmi-age').value),
g=document.getElementById('bmi-gender').value;
if(!h||!w||!a||h<50||h>250||w<10||w>500){{alert('请输入有效的身体数据');return;}}
var hm=h/100,bmi=Math.round(w/(hm*hm)*10)/10,
h_low=Math.round(18.5*hm*hm*10)/10,h_high=Math.round(23.9*hm*hm*10)/10,
cat,color,risk,advice,level;
if(bmi<18.5){{cat='偏瘦';color='#3b82f6';risk='低体重可能导致营养不良、免疫力下降、骨质疏松等问题';level='低';
advice='建议适当增加优质蛋白摄入（如鸡蛋、鱼虾、瘦肉、豆制品），搭配山药、红枣等健脾益气食材进行日常食养调理。建议每周进行3-4次中等强度运动，配合充足的睡眠。';}}
else if(bmi<24){{cat='正常';color='#22c55e';risk='体重在健康范围内，继续保持良好的生活习惯';level='低';
advice='当前体重在健康范围内。建议继续保持均衡饮食和规律运动。可关注药食同源食材的日常保健搭配，如枸杞代茶饮、百合莲子粥等。';}}
else if(bmi<28){{cat='超重';color='#f59e0b';risk='超重会增加心血管疾病、2型糖尿病等慢性病的风险';level='中等';
advice='建议控制高糖高脂饮食，增加膳食纤维摄入（如薏苡仁、荷叶、山楂等）。推荐每周进行150分钟以上中等强度有氧运动。可尝试药食同源方案辅助调理代谢功能。';}}
else{{cat='肥胖';color='#ef4444';risk='肥胖显著增加高血压、糖尿病、脂肪肝等多种慢性病风险';level='较高';
advice='建议在专业健康管理顾问指导下制定综合调理方案。饮食上可选用荷叶、山楂、决明子等辅助食材。运动应循序渐进，避免剧烈运动。建议先进行体质评估以获取个性化方案。';}}
document.getElementById('bmi-value').textContent=bmi;
var catEl=document.getElementById('bmi-category');
catEl.textContent=cat;catEl.style.background=color+'18';catEl.style.color=color;
document.getElementById('bmi-detail').innerHTML='健康风险等级：<strong>'+level+'</strong><br>理想体重范围：<strong>'+h_low+' - '+h_high+' kg</strong><br>'+risk;
document.getElementById('bmi-advice').innerHTML='<strong>个性化建议：</strong>'+advice;
document.getElementById('bmi-result').classList.add('visible');}}
</script>"""

    return _make_page_html(
        title=title, meta_desc=meta_desc, meta_keywords=meta_keywords,
        canonical_url=canonical, tool_name="BMI计算器",
        schema_json_list=[_BMI_SCHEMA, _BMI_FAQ_SCHEMA],
        faq_items=[
            {"question": "BMI 是什么？怎么计算？", "answer": "BMI（体质指数）= 体重(kg) / 身高(m)的平方。例如身高170cm、体重65kg，BMI = 65 / 1.7² = 22.5。"},
            {"question": "中国人的 BMI 正常范围是多少？", "answer": "中国成人标准：偏瘦 < 18.5，正常 18.5-23.9，超重 24-27.9，肥胖 >= 28。本工具已采用中国标准。"},
            {"question": "BMI 有什么局限性？", "answer": "BMI 不能区分肌肉和脂肪比例，健身人群 BMI 可能偏高但体脂正常。建议结合体脂率和腰围综合评估。"},
            {"question": "如何科学控制体重？", "answer": "综合饮食管理、规律运动和充足睡眠，通过体质评估了解自身特点，制定个性化食养调理方案。"},
        ],
        cta_text="注册获取个性化体质分析方案", cta_points="免费100积分",
        body_html=body,
    )


# ============================================================================
# 2. 睡眠质量评分器
# ============================================================================

class SleepScoreRequest(BaseModel):
    sleep_hours: float = Field(..., ge=0, le=24, description="睡眠时长(小时)")
    fall_asleep_minutes: int = Field(..., ge=0, le=180, description="入睡用时(分钟)")
    wake_frequency: int = Field(..., ge=0, le=20, description="夜间醒来次数")
    quality_rate: int = Field(..., ge=1, le=10, description="自我评分(1-10)")
    caffeine_cups: int = Field(0, ge=0, le=20, description="咖啡因摄入(杯)")
    screen_minutes: int = Field(0, ge=0, le=480, description="睡前屏幕时间(分钟)")


def _sleep_result(data: SleepScoreRequest) -> dict:
    """计算睡眠质量评分"""
    # 各维度评分（满分不同，最后加权）
    # 时长评分 (0-25): 7-9小时最佳
    hours = data.sleep_hours
    if 7 <= hours <= 9:
        duration_score = 25
    elif 6 <= hours < 7 or 9 < hours <= 10:
        duration_score = 20
    elif 5 <= hours < 6:
        duration_score = 14
    elif hours < 5:
        duration_score = 8
    else:
        duration_score = 10

    # 入睡速度评分 (0-25): 15分钟内最佳
    mins = data.fall_asleep_minutes
    if mins <= 10:
        latency_score = 25
    elif mins <= 20:
        latency_score = 22
    elif mins <= 30:
        latency_score = 18
    elif mins <= 60:
        latency_score = 12
    else:
        latency_score = 6

    # 连续性评分 (0-25): 不醒或醒1次最佳
    wakes = data.wake_frequency
    if wakes == 0:
        continuity_score = 25
    elif wakes == 1:
        continuity_score = 22
    elif wakes == 2:
        continuity_score = 16
    elif wakes <= 4:
        continuity_score = 10
    else:
        continuity_score = 5

    # 主观评分 (0-25): 自评 * 2.5
    subjective_score = data.quality_rate * 2.5

    total = int(duration_score + latency_score + continuity_score + subjective_score)
    total = min(total, 100)

    # 影响因子
    factors = []
    if duration_score < 20:
        factors.append("睡眠时长不理想" if hours < 7 else "睡眠时长偏长")
    if latency_score < 18:
        factors.append("入睡时间过长")
    if continuity_score < 16:
        factors.append("夜间频繁醒来")
    if data.caffeine_cups >= 3:
        factors.append("咖啡因摄入过多")
    if data.screen_minutes >= 60:
        factors.append("睡前屏幕时间过长")

    # 评分等级
    if total >= 85:
        category = "优秀"
        cat_color = "#22c55e"
    elif total >= 70:
        category = "良好"
        cat_color = "#11998e"
    elif total >= 50:
        category = "一般"
        cat_color = "#f59e0b"
    else:
        category = "较差"
        cat_color = "#ef4444"

    # 改善建议
    tips = []
    if duration_score < 20:
        tips.append("尝试固定作息时间，每天同一时间入睡和起床")
    if latency_score < 18:
        tips.append("睡前1小时避免强光刺激，可尝试酸枣仁、百合代茶饮")
    if continuity_score < 16:
        tips.append("保持卧室安静黑暗，注意腹部保暖")
    if data.caffeine_cups >= 3:
        tips.append("下午2点后避免摄入咖啡因，可用罗汉果茶替代")
    if data.screen_minutes >= 60:
        tips.append("睡前1小时放下手机，可做呼吸放松练习")
    if not tips:
        tips.append("继续保持良好的睡眠习惯，注意季节性作息调整")

    return {
        "score": total,
        "category": category,
        "cat_color": cat_color,
        "duration_score": int(duration_score),
        "latency_score": int(latency_score),
        "continuity_score": int(continuity_score),
        "subjective_score": int(subjective_score),
        "factors": factors,
        "tips": tips,
    }


_SLEEP_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "睡眠质量评分器",
    "description": "免费在线睡眠质量自测工具，评估睡眠时长、入睡速度、连续性等维度，获取个性化睡眠修复建议",
    "url": f"{BASE_URL}/tools/sleep-score-calculator",
    "applicationCategory": "HealthApplication",
    "operatingSystem": "Web",
    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
    "author": {"@type": "Organization", "name": SITE_NAME},
    "inLanguage": "zh-CN",
}

_SLEEP_FAQ_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "成年人每天睡多久比较好？",
            "acceptedAnswer": {"@type": "Answer", "text": "根据美国睡眠基金会建议，成年人（18-64岁）每天需要7-9小时睡眠。中医子午流注理论也建议在子时（23:00-01:00）前入睡，此时段是肝胆经当令，有助于身体修复。"},
        },
        {
            "@type": "Question",
            "name": "入睡困难怎么办？",
            "acceptedAnswer": {"@type": "Answer", "text": "入睡困难可通过多种方式缓解：睡前1小时减少屏幕时间、保持卧室温度适宜、避免睡前咖啡因摄入。中医方面，酸枣仁、百合、龙眼肉等药食同源食材有养心安神的功效，可作为代茶饮辅助调理。"},
        },
        {
            "@type": "Question",
            "name": "什么是睡眠修复？和安眠药有什么区别？",
            "acceptedAnswer": {"@type": "Answer", "text": "睡眠修复是通过调理体质、恢复自然睡眠节律来改善睡眠质量的方法，核心在于解决根源问题。与安眠药不同，睡眠修复不依赖药物介入，而是通过生活方式调整、药食同源食材搭配等方式，帮助身体恢复自然的睡眠能力。"},
        },
        {
            "@type": "Question",
            "name": "夜间频繁醒来是什么原因？",
            "acceptedAnswer": {"@type": "Answer", "text": "夜间频繁醒来可能与多种因素有关：压力和焦虑、睡前饮食过饱、环境温度不适宜、阴虚火旺等体质偏颇。建议结合体质评估找到根源，针对性调理可显著改善。"},
        },
    ],
}


def _build_sleep_page() -> str:
    """构建睡眠质量评分器完整 HTML 页面"""
    title = "免费睡眠质量评分器 - 在线睡眠自测"
    meta_desc = "免费在线睡眠质量自测工具，6个维度评估你的睡眠健康。获取个性化睡眠修复建议，结合中医子午流注理论，帮你找回好睡眠。"
    meta_keywords = "睡眠质量评分,睡眠自测,睡眠修复,入睡困难,失眠调理,睡眠计算器,中医睡眠,子午流注,免费睡眠测试"
    canonical = f"{BASE_URL}/tools/sleep-score-calculator"

    body = """<div class="card">
<h2>睡眠数据评估</h2>
<div class="form-group">
<label>平均睡眠时长: <span class="slider-value" id="sleep-h-val">7</span> 小时</label>
<input type="range" id="sleep-hours" min="0" max="16" step="0.5" value="7" oninput="document.getElementById('sleep-h-val').textContent=this.value">
</div>
<div class="form-group">
<label>平均入睡用时: <span class="slider-value" id="sleep-f-val">15</span> 分钟</label>
<input type="range" id="sleep-fall" min="0" max="120" step="5" value="15" oninput="document.getElementById('sleep-f-val').textContent=this.value">
</div>
<div class="form-row">
<div class="form-group">
<label>夜间醒来次数: <span class="slider-value" id="sleep-w-val">1</span> 次</label>
<input type="range" id="sleep-wake" min="0" max="10" step="1" value="1" oninput="document.getElementById('sleep-w-val').textContent=this.value">
</div>
<div class="form-group">
<label>睡眠自我评分: <span class="slider-value" id="sleep-q-val">6</span> / 10</label>
<input type="range" id="sleep-quality" min="1" max="10" step="1" value="6" oninput="document.getElementById('sleep-q-val').textContent=this.value">
</div>
</div>
<div class="form-row">
<div class="form-group">
<label>日均咖啡因摄入: <span class="slider-value" id="sleep-c-val">1</span> 杯</label>
<input type="range" id="sleep-caffeine" min="0" max="10" step="1" value="1" oninput="document.getElementById('sleep-c-val').textContent=this.value">
</div>
<div class="form-group">
<label>睡前屏幕时间: <span class="slider-value" id="sleep-s-val">30</span> 分钟</label>
<input type="range" id="sleep-screen" min="0" max="240" step="10" value="30" oninput="document.getElementById('sleep-s-val').textContent=this.value">
</div>
</div>
<button class="btn-calc" onclick="calcSleep()">评估我的睡眠质量</button>
<div class="result-box" id="sleep-result">
<div class="score-big" id="sleep-score"></div>
<div class="category" id="sleep-category"></div>
<div class="detail" id="sleep-detail"></div>
<div class="advice" id="sleep-tips"></div>
</div>
</div>
<script>
function calcSleep(){{
var h=parseFloat(document.getElementById('sleep-hours').value),
f=parseInt(document.getElementById('sleep-fall').value),
w=parseInt(document.getElementById('sleep-wake').value),
q=parseInt(document.getElementById('sleep-quality').value),
c=parseInt(document.getElementById('sleep-caffeine').value),
s=parseInt(document.getElementById('sleep-screen').value);
/* duration 0-25 */
var ds;
if(h>=7&&h<=9)ds=25;else if((h>=6&&h<7)||(h>9&&h<=10))ds=20;else if(h>=5&&h<6)ds=14;else if(h<5)ds=8;else ds=10;
/* latency 0-25 */
var ls;
if(f<=10)ls=25;else if(f<=20)ls=22;else if(f<=30)ls=18;else if(f<=60)ls=12;else ls=6;
/* continuity 0-25 */
var cs;
if(w===0)cs=25;else if(w===1)cs=22;else if(w===2)cs=16;else if(w<=4)cs=10;else cs=5;
/* subjective 0-25 */
var ss=q*2.5;
var total=Math.min(100,Math.round(ds+ls+cs+ss)),cat,color;
if(total>=85){{cat='优秀';color='#22c55e'}}else if(total>=70){{cat='良好';color='#11998e'}}else if(total>=50){{cat='一般';color='#f59e0b'}}else{{cat='较差';color='#ef4444'}}
var factors=[];
if(ds<20)factors.push(h<7?'睡眠时长不足':'睡眠时长偏长');
if(ls<18)factors.push('入睡时间过长');
if(cs<16)factors.push('夜间频繁醒来');
if(c>=3)factors.push('咖啡因摄入过多');
if(s>=60)factors.push('睡前屏幕时间过长');
var tips=[];
if(ds<20)tips.push('尝试固定作息时间，每天同一时间入睡和起床');
if(ls<18)tips.push('睡前1小时避免强光刺激，可尝试酸枣仁、百合代茶饮');
if(cs<16)tips.push('保持卧室安静黑暗，注意腹部保暖');
if(c>=3)tips.push('下午2点后避免咖啡因，可用罗汉果茶替代');
if(s>=60)tips.push('睡前1小时放下手机，可做呼吸放松练习');
if(!tips.length)tips.push('继续保持良好的睡眠习惯，注意季节性作息调整');
document.getElementById('sleep-score').textContent=total+'分';
var catEl=document.getElementById('sleep-category');
catEl.textContent=cat;catEl.style.background=color+'18';catEl.style.color=color;
var dim='时长:'+ds+'/25 | 入睡:'+ls+'/25 | 连续:'+cs+'/25 | 主观:'+Math.round(ss)+'/25';
var fac=factors.length?'主要影响因素：'+factors.join('、'):'暂无明显影响因素';
document.getElementById('sleep-detail').innerHTML='<strong>各维度得分</strong><br>'+dim+'<br><br>'+fac;
document.getElementById('sleep-tips').innerHTML='<strong>改善建议：</strong><br>'+tips.map(function(t){{return '• '+t}}).join('<br>');
document.getElementById('sleep-result').classList.add('visible');}}
</script>"""

    return _make_page_html(
        title=title, meta_desc=meta_desc, meta_keywords=meta_keywords,
        canonical_url=canonical, tool_name="睡眠质量评分器",
        schema_json_list=[_SLEEP_SCHEMA, _SLEEP_FAQ_SCHEMA],
        faq_items=[
            {"question": "成年人每天睡多久比较好？", "answer": "成年人（18-64岁）建议每天7-9小时。中医子午流注理论建议在子时（23:00-01:00）前入睡，此时肝胆经当令，利于身体修复。"},
            {"question": "入睡困难怎么办？", "answer": "睡前1小时减少屏幕时间、保持卧室温度适宜。酸枣仁、百合、龙眼肉等药食同源食材有养心安神功效，可作代茶饮辅助调理。"},
            {"question": "什么是睡眠修复？和安眠药有什么区别？", "answer": "睡眠修复通过调理体质、恢复自然睡眠节律来改善睡眠质量，不依赖药物介入，而是通过生活方式调整和药食同源搭配帮助恢复自然睡眠能力。"},
            {"question": "夜间频繁醒来是什么原因？", "answer": "可能与压力焦虑、睡前饮食过饱、环境温度不适宜、阴虚火旺等体质偏颇有关。建议结合体质评估找到根源，针对性调理。"},
        ],
        cta_text="注册获取AI睡眠修复方案", cta_points="免费100积分",
        body_html=body,
    )


# ============================================================================
# 3. 中医体质自测
# ============================================================================

class TCMTestRequest(BaseModel):
    answers: dict[str, int] = Field(..., description="题目ID到选项分数(1-4)的映射")


# 9种体质问卷数据
TCM_CONSTITUTIONS = {
    "pinghe": {
        "name": "平和质",
        "color": "#22c55e",
        "desc": "阴阳气血调和，体态适中，面色润泽，精力充沛，睡眠良好，二便正常。是最理想的体质状态。",
        "diet": "保持均衡饮食即可，顺应四时变化灵活调整。可适当食用山药、茯苓等平和食材日常保健。",
    },
    "qixu": {
        "name": "气虚质",
        "color": "#3b82f6",
        "desc": "元气不足，容易疲乏，气短懒言，容易出汗，舌淡脉弱。抵抗力较弱，容易感冒。",
        "diet": "宜选用补气健脾食材，如黄芪、山药、红枣、人参。避免过于辛散耗气的食物。建议规律运动，避免过度劳累。",
    },
    "yangxu": {
        "name": "阳虚质",
        "color": "#6366f1",
        "desc": "阳气不足，手足不温，畏寒怕冷，面色苍白，喜热饮食，精神不振。",
        "diet": "宜温补阳气，如生姜、肉桂、核桃仁、杜仲。少吃寒凉食物，注意腹部和下肢保暖。",
    },
    "yinxu": {
        "name": "阴虚质",
        "color": "#f59e0b",
        "desc": "阴液亏少，口燥咽干，手足心热，潮热盗汗，大便干燥，舌红少苔。",
        "diet": "宜滋阴润燥，如百合、麦冬、桑葚、黑芝麻。少食辛辣燥热之品，避免熬夜。",
    },
    "tanshi": {
        "name": "痰湿质",
        "color": "#8b5cf6",
        "desc": "痰湿凝聚，体形肥胖，腹部肥满松软，口中粘腻，身重不爽，舌苔白腻。",
        "diet": "宜健脾化湿，如薏苡仁、茯苓、荷叶、陈皮。少食肥甘厚腻，适度运动促进代谢。",
    },
    "shire": {
        "name": "湿热质",
        "color": "#ef4444",
        "desc": "湿热内蕴，面垢油光，口苦口干，身重困倦，大便粘滞，舌红苔黄腻。",
        "diet": "宜清热利湿，如金银花、菊花、薏苡仁、薄荷。少食辛辣油腻，保持居室通风干燥。",
    },
    "xueyu": {
        "name": "血瘀质",
        "color": "#ec4899",
        "desc": "血行不畅，肤色晦暗，色素沉着，容易出现瘀斑，唇色暗紫，舌质紫暗有瘀点。",
        "diet": "宜活血化瘀，如山楂、当归、红花。适度运动促进气血运行，避免久坐不动。",
    },
    "qiyu": {
        "name": "气郁质",
        "color": "#14b8a6",
        "desc": "气机郁滞，神情抑郁，情感脆弱，烦闷不乐，多愁善感，胸胁胀满。",
        "diet": "宜疏肝理气，如玫瑰花、陈皮、薄荷、菊花。注意情志调摄，培养兴趣爱好，保持社交活动。",
    },
    "tebing": {
        "name": "特禀质",
        "color": "#f97316",
        "desc": "先天特殊，过敏体质，容易对花粉、食物、药物等过敏，皮肤易起荨麻疹，鼻塞打喷嚏。",
        "diet": "饮食清淡，避免已知过敏原。可适量食用黄芪增强卫气。建议进行过敏原检测，针对性回避。",
    },
}

# 每种体质5道题目，选项：从不(1) 偶尔(2) 经常(3) 总是(4)
TCM_QUESTIONS = {
    "pinghe": [
        {"id": "p1", "q": "你精力充沛，不容易感到疲劳吗？"},
        {"id": "p2", "q": "你睡眠质量好，醒来后感觉精力恢复了吗？"},
        {"id": "p3", "q": "你食欲正常，消化功能良好吗？"},
        {"id": "p4", "q": "你适应外界环境变化的能力强吗？"},
        {"id": "p5", "q": "你二便（大小便）规律正常吗？"},
    ],
    "qixu": [
        {"id": "qx1", "q": "你容易感到疲乏，说话声音低弱吗？"},
        {"id": "qx2", "q": "你容易出虚汗（稍微活动就出汗）吗？"},
        {"id": "qx3", "q": "你容易感冒，抵抗力较差吗？"},
        {"id": "qx4", "q": "你感觉气短，呼吸浅促吗？"},
        {"id": "qx5", "q": "你运动后容易累，恢复较慢吗？"},
    ],
    "yangxu": [
        {"id": "yx1", "q": "你手脚冰凉，怕冷吗？"},
        {"id": "yx2", "q": "你喜欢吃热食热饮吗？"},
        {"id": "yx3", "q": "你精神不振，容易萎靡吗？"},
        {"id": "yx4", "q": "你吃冷食后容易感到不适（腹痛、腹泻）吗？"},
        {"id": "yx5", "q": "你面色偏白，缺乏血色吗？"},
    ],
    "yinxu": [
        {"id": "yy1", "q": "你经常感到口干舌燥吗？"},
        {"id": "yy2", "q": "你手脚心容易发热吗？"},
        {"id": "yy3", "q": "你容易盗汗（睡觉时出汗）吗？"},
        {"id": "yy4", "q": "你大便偏干，排便不畅吗？"},
        {"id": "yy5", "q": "你容易感到心烦急躁吗？"},
    ],
    "tanshi": [
        {"id": "ts1", "q": "你感觉身体沉重，行动不爽快吗？"},
        {"id": "ts2", "q": "你腹部肥满松软吗？"},
        {"id": "ts3", "q": "你口中感觉黏腻不清爽吗？"},
        {"id": "ts4", "q": "你额头、鼻部油脂分泌较多吗？"},
        {"id": "ts5", "q": "你舌苔厚腻吗？"},
    ],
    "shire": [
        {"id": "sr1", "q": "你面部和鼻尖容易出油吗？"},
        {"id": "sr2", "q": "你常感到口苦口干吗？"},
        {"id": "sr3", "q": "你容易生痤疮（青春痘）吗？"},
        {"id": "sr4", "q": "你常感到身重困倦吗？"},
        {"id": "sr5", "q": "你大便粘滞不爽，容易粘马桶吗？"},
    ],
    "xueyu": [
        {"id": "xy1", "q": "你面色晦暗，嘴唇颜色偏紫吗？"},
        {"id": "xy2", "q": "你皮肤容易有瘀斑或青紫吗？"},
        {"id": "xy3", "q": "你身体某些部位常有刺痛感吗？"},
        {"id": "xy4", "q": "你舌质偏紫暗或有瘀点吗？"},
        {"id": "xy5", "q": "你面色或眼眶周围偏暗吗？"},
    ],
    "qiyu": [
        {"id": "qy1", "q": "你经常感到情绪低落或抑郁吗？"},
        {"id": "qy2", "q": "你容易多愁善感，情感脆弱吗？"},
        {"id": "qy3", "q": "你经常感到胸闷或胸胁胀满吗？"},
        {"id": "qy4", "q": "你容易唉声叹气吗？"},
        {"id": "qy5", "q": "你容易感到咽喉部有异物感（咽中如有炙脔）吗？"},
    ],
    "tebing": [
        {"id": "tb1", "q": "你没有感冒也会打喷嚏吗？"},
        {"id": "tb2", "q": "你没有感冒也会鼻塞流涕吗？"},
        {"id": "tb3", "q": "你容易对花粉、食物、药物等过敏吗？"},
        {"id": "tb4", "q": "你皮肤容易起荨麻疹或风团吗？"},
        {"id": "tb5", "q": "你对季节交替或环境变化特别敏感吗？"},
    ],
}


def _tcm_test_result(answers: dict[str, int]) -> dict:
    """计算体质自测结果"""
    # 统计各体质分数
    scores = {}
    max_scores = {}
    for key in TCM_CONSTITUTIONS:
        scores[key] = 0
        max_scores[key] = 0

    for qid, score in answers.items():
        # 找到题目属于哪种体质
        for const_key, questions in TCM_QUESTIONS.items():
            for question in questions:
                if question["id"] == qid:
                    scores[const_key] += score
                    max_scores[const_key] += 4  # 最大分4
                    break

    # 计算转化分 (0-100)
    result_scores = {}
    for key in TCM_CONSTITUTIONS:
        raw = scores[key]
        max_s = max_scores[key] if max_scores[key] > 0 else 1
        converted = int(raw / max_s * 100)
        result_scores[key] = converted

    # 找主要体质
    dominant = max(result_scores, key=result_scores.get)
    dominant_score = result_scores[dominant]

    # 判断是否偏颇（转化分 >= 40 为偏颇倾向）
    is_biased = dominant_score >= 40

    return {
        "scores": result_scores,
        "dominant": dominant,
        "dominant_name": TCM_CONSTITUTIONS[dominant]["name"],
        "dominant_score": dominant_score,
        "is_biased": is_biased,
        "dominant_desc": TCM_CONSTITUTIONS[dominant]["desc"],
        "dominant_diet": TCM_CONSTITUTIONS[dominant]["diet"],
        "dominant_color": TCM_CONSTITUTIONS[dominant]["color"],
    }


_TCM_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "中医体质自测",
    "description": "基于中华中医药学会标准的九种体质自测工具，45道题目快速评估你的体质类型，获取个性化药食同源调理方案",
    "url": f"{BASE_URL}/tools/tcm-constitution-test",
    "applicationCategory": "HealthApplication",
    "operatingSystem": "Web",
    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
    "author": {"@type": "Organization", "name": SITE_NAME},
    "inLanguage": "zh-CN",
}

_TCM_FAQ_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "什么是九种体质？",
            "acceptedAnswer": {"@type": "Answer", "text": "九种体质是中华中医药学会发布的《中医体质分类与判定》标准中定义的体质分类，包括平和质、气虚质、阳虚质、阴虚质、痰湿质、湿热质、血瘀质、气郁质、特禀质。每个人可能以一种体质为主，兼有其他体质特征。"},
        },
        {
            "@type": "Question",
            "name": "体质可以改变吗？",
            "acceptedAnswer": {"@type": "Answer", "text": "可以。体质虽然有一定的遗传基础，但并非一成不变。通过饮食调理、运动锻炼、情志调摄和规律作息，偏颇体质可以得到改善，趋向平和质。这就是中医'治未病'理念的核心。"},
        },
        {
            "@type": "Question",
            "name": "什么是药食同源？",
            "acceptedAnswer": {"@type": "Answer", "text": "药食同源是指既是食品又是中药材的物质，国家卫健委已公布多批药食同源目录。这些食材如山药、枸杞、红枣等，既是日常食物，又具有药用价值，可在日常饮食中长期食用起到调理体质的作用。"},
        },
        {
            "@type": "Question",
            "name": "这个自测结果准确吗？",
            "acceptedAnswer": {"@type": "Answer", "text": "本工具基于简化版中医体质问卷，可初步判断体质倾向，但无法替代专业中医师的体质辨识。建议将此结果作为参考，结合专业体质评估获取更精准的个性化调理方案。"},
        },
    ],
}


def _build_tcm_page() -> str:
    """构建中医体质自测完整 HTML 页面"""
    title = "中医体质测试 - 免费9种体质自测"
    meta_desc = "基于中华中医药学会标准，45道题目快速辨识你的中医体质类型（平和质/气虚质/阳虚质等9种），获取个性化药食同源调理方案和饮食建议。"
    meta_keywords = "中医体质测试,九种体质,体质自测,平和质,气虚质,阳虚质,阴虚质,痰湿质,湿热质,血瘀质,气郁质,特禀质,药食同源,体质调理,免费体质测试"
    canonical = f"{BASE_URL}/tools/tcm-constitution-test"

    # Pre-build JS data objects (avoid nested f-strings)
    consts_js = ",".join(
        '"' + k + '":{"name":"' + v["name"] + '","color":"' + v["color"] + '"}'
        for k, v in TCM_CONSTITUTIONS.items()
    )
    qmap_js = ",".join(
        '"' + q["id"] + '":"' + ck + '"'
        for ck, qs in TCM_QUESTIONS.items() for q in qs
    )
    descs_js = ",".join(
        '"' + k + '":"' + v["desc"].replace('"', "'") + '"'
        for k, v in TCM_CONSTITUTIONS.items()
    )
    diets_js = ",".join(
        '"' + k + '":"' + v["diet"].replace('"', "'") + '"'
        for k, v in TCM_CONSTITUTIONS.items()
    )

    # 生成所有题目的 HTML
    questions_html = ""
    for const_key, questions in TCM_QUESTIONS.items():
        const_name = TCM_CONSTITUTIONS[const_key]["name"]
        questions_html += '<div class="card"><h2>' + const_name + '</h2>'
        for q in questions:
            questions_html += (
                '<div class="form-group">'
                '<p style="font-size:.9rem;margin-bottom:.3rem">' + q["q"] + '</p>'
                '<div class="radio-group">'
                '<label><input type="radio" name="' + q["id"] + '" value="1"> 从不</label>'
                '<label><input type="radio" name="' + q["id"] + '" value="2"> 偶尔</label>'
                '<label><input type="radio" name="' + q["id"] + '" value="3"> 经常</label>'
                '<label><input type="radio" name="' + q["id"] + '" value="4"> 总是</label>'
                '</div></div>'
            )
        questions_html += '</div>'

    # 分数颜色条
    bar_items = ""
    for key, info in TCM_CONSTITUTIONS.items():
        bar_items += (
            '<div class="constitution-bar-wrap">'
            '<div class="constitution-bar-label"><span>' + info["name"] + '</span>'
            '<span id="bar-' + key + '-val">0</span></div>'
            '<div class="constitution-bar"><div class="constitution-bar-fill" id="bar-' + key + '" '
            'style="width:0%;background:' + info["color"] + '"></div></div></div>'
        )

    # Build JS block separately (no f-string to avoid brace conflicts)
    js_block = """
<script>
var CONSTS={""" + consts_js + """};
function calcTCM(){
var allScores={};
for(var k in CONSTS){allScores[k]=0;}
var radios=document.querySelectorAll('input[type=radio]:checked');
if(radios.length<30){alert('请至少回答30道题目再提交');return;}
var qMap={""" + qmap_js + """};
radios.forEach(function(r){var k=qMap[r.name];if(k){allScores[k]+=parseInt(r.value);}});
var result={};
for(var k in CONSTS){var raw=allScores[k],maxS=20;
var converted=Math.round(raw/maxS*100);
result[k]=converted;}
var dominant=Object.keys(result).reduce(function(a,b){return result[a]>result[b]?a:b});
var domScore=result[dominant],domName=CONSTS[dominant].name,domColor=CONSTS[dominant].color;
var isBiased=domScore>=40;
document.getElementById('tcm-score').textContent=domScore+'分';
var catEl=document.getElementById('tcm-category');
catEl.textContent=isBiased?'体质偏颇倾向：'+domName:'体质基本平和';
catEl.style.background=domColor+'18';catEl.style.color=domColor;
for(var k in result){var bar=document.getElementById('bar-'+k);
if(bar){bar.style.width=Math.min(result[k],100)+'%';}
var valEl=document.getElementById('bar-'+k+'-val');
if(valEl){valEl.textContent=result[k];}}
document.getElementById('tcm-bars-card').style.display='block';
var descs={""" + descs_js + """};
var diets={""" + diets_js + """};
document.getElementById('tcm-detail').innerHTML='<strong>你的主要体质倾向：'+domName+'</strong><br>'+descs[dominant];
document.getElementById('tcm-diet').innerHTML='<strong>饮食调理建议：</strong><br>'+diets[dominant];
document.getElementById('tcm-result').classList.add('visible');}
</script>"""

    body = (
        questions_html
        + '<button class="btn-calc" onclick="calcTCM()">提交并获取体质分析</button>'
        + '<div class="result-box" id="tcm-result">'
        + '<div class="score-big" id="tcm-score"></div>'
        + '<div class="category" id="tcm-category"></div>'
        + '<div class="detail" id="tcm-detail"></div>'
        + '<div class="advice" id="tcm-diet"></div>'
        + '</div>'
        + '<div class="card" id="tcm-bars-card" style="display:none"><h2>九种体质得分分布</h2>'
        + bar_items + '</div>'
        + js_block
    )

    return _make_page_html(
        title=title, meta_desc=meta_desc, meta_keywords=meta_keywords,
        canonical_url=canonical, tool_name="中医体质自测",
        schema_json_list=[_TCM_SCHEMA, _TCM_FAQ_SCHEMA],
        faq_items=[
            {"question": "什么是九种体质？", "answer": "中华中医药学会发布的标准体质分类，包括平和质、气虚质、阳虚质、阴虚质、痰湿质、湿热质、血瘀质、气郁质、特禀质。每个人可能以一种为主，兼有其他体质特征。"},
            {"question": "体质可以改变吗？", "answer": "可以。体质虽有一定遗传基础，但通过饮食调理、运动锻炼、情志调摄和规律作息，偏颇体质可改善趋向平和质。"},
            {"question": "什么是药食同源？", "answer": "药食同源指既是食品又是中药材的物质，如山药、枸杞、红枣等，可在日常饮食中长期食用起调理体质作用。"},
            {"question": "自测结果准确吗？", "answer": "本工具为简化版问卷，可初步判断体质倾向，但不能替代专业中医师的体质辨识。建议结合专业评估获取更精准方案。"},
        ],
        cta_text="注册获取个性化药食同源调理方案", cta_points="30积分",
        body_html=body,
    )


# ============================================================================
# 4. 药食同源食材查询
# ============================================================================

class FoodSearchRequest(BaseModel):
    keyword: str = Field("", description="搜索关键词")
    nature: str = Field("", description="药性筛选: 寒/凉/平/温/热/微寒/微温")
    meridian: str = Field("", description="归经筛选")


# 药性归一化映射
_NATURE_MAP = {
    "寒": ["寒"],
    "凉": ["凉", "微寒"],
    "平": ["平"],
    "温": ["温", "微温"],
    "热": ["热"],
}

# 归经列表
_ALL_MERIDIANS = sorted(set(
    m.strip()
    for herb in FOOD_MEDICINE_HOMOLOGY
    for m in herb["meridian"].split("、")
))


def _food_search(keyword: str = "", nature: str = "", meridian: str = "") -> list[dict]:
    """搜索药食同源食材"""
    results = []
    for herb in FOOD_MEDICINE_HOMOLOGY:
        # 关键词搜索
        if keyword:
            kw = keyword.lower()
            searchable = (herb["name"] + herb["effect"] + herb["nature"] + herb["meridian"]).lower()
            if kw not in searchable:
                continue
        # 药性筛选
        if nature:
            # 归一化筛选
            valid_natures = _NATURE_MAP.get(nature, [nature])
            herb_nature = herb["nature"]
            if herb_nature not in valid_natures and not any(
                herb_nature in _NATURE_MAP.get(n, []) for n in [nature]
            ):
                # 直接匹配
                if herb_nature != nature and herb_nature not in _NATURE_MAP.get(nature, []):
                    continue
        # 归经筛选
        if meridian:
            if meridian not in herb["meridian"]:
                continue

        # 构建结果
        slug = herb["name"].replace(" ", "-") + "-food-medicine"
        results.append({
            "name": herb["name"],
            "nature": herb["nature"],
            "meridian": herb["meridian"],
            "effect": herb["effect"],
            "slug": slug,
            "url": f"{BASE_URL}/knowledge/{slug}",
        })
    return results


_FOOD_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "药食同源食材查询",
    "description": "查询28种国家卫健委公布的药食同源食材，按药性、归经筛选，了解每种食材的功效和用法",
    "url": f"{BASE_URL}/tools/food-medicine-query",
    "applicationCategory": "HealthApplication",
    "operatingSystem": "Web",
    "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
    "author": {"@type": "Organization", "name": SITE_NAME},
    "inLanguage": "zh-CN",
}

_FOOD_FAQ_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "什么是药食同源？",
            "acceptedAnswer": {"@type": "Answer", "text": "药食同源是指既是食品又是中药材的物质。国家卫健委已公布多批药食同源目录，这些食材在日常生活中可安全食用，同时又具有调理体质的功效。如山药、枸杞、红枣、生姜等都是常见的药食同源食材。"},
        },
        {
            "@type": "Question",
            "name": "药食同源食材有副作用吗？",
            "acceptedAnswer": {"@type": "Answer", "text": "药食同源食材在常规用量下安全性较高，但并非完全没有注意事项。体质偏寒的人不宜过多食用寒性食材，体质偏热的人不宜过多食用温热食材。孕妇和慢性病患者应咨询专业人士。"},
        },
        {
            "@type": "Question",
            "name": "如何根据体质选择食材？",
            "acceptedAnswer": {"@type": "Answer", "text": "不同体质适合不同药性的食材。气虚质宜选用温平补气的食材（如黄芪、山药），阳虚质宜温补（如生姜、核桃仁），阴虚质宜滋阴（如百合、桑葚），痰湿质宜健脾化湿（如薏苡仁、茯苓）。建议先进行体质评估再选择。"},
        },
        {
            "@type": "Question",
            "name": "药食同源食材每天吃多少合适？",
            "acceptedAnswer": {"@type": "Answer", "text": "一般干品建议每天10-30克，鲜品可适当增加。具体用量因体质和食材而异。作为日常保健，建议少量多样，长期坚持比大量短期更有效。可参考每种食材的详细页面了解推荐用量。"},
        },
    ],
}


def _build_food_page() -> str:
    """构建药食同源食材查询完整 HTML 页面"""
    title = "药食同源食材查询 - 28种药食同源食材大全"
    meta_desc = "查询28种国家卫健委公布的药食同源食材，按药性(寒凉温热平)、归经筛选，了解每种食材的功效、用法和搭配方案。"
    meta_keywords = "药食同源,中药食材,食疗食材,药食同源目录,药性查询,归经查询,食疗方案,中医食材大全,养生食材"
    canonical = f"{BASE_URL}/tools/food-medicine-query"

    # 生成食材数据 JS
    herbs_json = json.dumps(
        [
            {
                "name": h["name"],
                "nature": h["nature"],
                "meridian": h["meridian"],
                "effect": h["effect"],
                "slug": h["name"].replace(" ", "-") + "-food-medicine",
            }
            for h in FOOD_MEDICINE_HOMOLOGY
        ],
        ensure_ascii=False,
    )
    # 转义以放入HTML
    herbs_json_escaped = herbs_json.replace("</", r"<\/")

    # 用法建议映射
    usage_map = {
        "山药": "可煮粥、炖汤、炒食。山药粥适合脾胃虚弱者日常调理。",
        "枸杞子": "可直接嚼食、泡茶、煲汤。建议每天10-20g，避免过量。",
        "生姜": "可做调味料、煮姜茶、姜汤驱寒。阴虚体质不宜多用。",
        "红枣": "可泡茶、煲汤、煮粥。建议每次3-5枚，去核食用更佳。",
        "莲子": "可煮粥、做甜品。莲子百合粥为经典安神助眠方。",
        "茯苓": "可研粉冲服、煮粥、煲汤。茯苓薏米粥利湿健脾效果好。",
        "黄芪": "可泡水代茶饮、炖鸡汤。补气升阳，感冒发热时不宜使用。",
        "薏苡仁": "可煮粥、煮水代茶饮。薏苡仁赤小豆汤为经典利湿方。",
        "芡实": "可煮粥、煲汤。芡实莲子粥补脾固肾效果佳。",
        "百合": "可煮粥、做甜品、泡茶。百合莲子粥养心安神。",
        "龙眼肉": "可直接食用、泡茶、煲汤。体质偏热者不宜多用。",
        "黑芝麻": "可研粉冲服、入丸剂、做糕点。润肠通便效果佳。",
        "核桃仁": "可直接食用、入菜、煲汤。补肾固精，每天3-5个为宜。",
        "陈皮": "可泡茶、做调味料、煲汤。理气化痰，越陈越好。",
        "山楂": "可泡茶、煮水、入菜。消食化积，胃酸过多者不宜。",
        "桑葚": "可直接食用、泡酒、煮粥。滋阴补血，新鲜为佳。",
        "菊花": "可泡茶、入菜。疏散风热、平肝明目，脾胃虚寒者不宜。",
        "金银花": "可泡茶、煮水。清热解毒，虚寒体质不宜长期饮用。",
        "薄荷": "可泡茶、做调味料。疏散风热，不宜久煎。",
        "决明子": "可泡茶、煮水。清肝明目、润肠通便，孕妇慎用。",
        "黄精": "可泡茶、炖汤、入丸剂。补气养阴，滋腻助湿，湿盛者不宜。",
        "阿胶": "可烊化冲服、入丸剂。补血滋阴，感冒期间不宜服用。",
        "酸枣仁": "可研末冲服、煮粥、泡茶。养心安神，为中医经典助眠药材。",
        "麦冬": "可泡茶、煮粥、入煎剂。养阴生津润肺，虚寒体质不宜。",
        "罗汉果": "可泡茶代水饮用。清热润肺利咽，甜味天然无热量。",
        "人参": "可泡水、炖汤、含服。大补元气，感冒发热时不宜。",
        "当归": "可泡茶、炖汤、入丸剂。补血活血调经，腹泻者不宜。",
        "杜仲": "可泡茶、炖汤、入丸剂。补肝肾强筋骨，阴虚火旺者慎用。",
        "荷叶": "可泡茶、煮粥、入菜。清热解暑，脾胃虚寒者不宜。",
        "白芷": "可做调味料、入煎剂。解表散寒，阴虚血热者不宜。",
    }

    # 使用建议 JS
    usage_json = json.dumps(usage_map, ensure_ascii=False).replace("</", r"<\/")

    body = f"""<div class="card">
<h2>搜索药食同源食材</h2>
<div class="search-wrap">
<input type="text" id="food-keyword" placeholder="输入食材名称或功效关键词..." oninput="searchFood()">
<select id="food-nature" onchange="searchFood()">
<option value="">全部药性</option>
<option value="寒">寒</option>
<option value="凉">凉</option>
<option value="平">平</option>
<option value="温">温</option>
<option value="热">热</option>
</select>
<select id="food-meridian" onchange="searchFood()">
<option value="">全部归经</option>
{"".join(f'<option value="{m}">{m}经</option>' for m in _ALL_MERIDIANS)}
</select>
</div>
<div class="search-results" id="food-results">
<p class="no-result">输入关键词或选择筛选条件开始查询</p>
</div>
</div>
<script>
var herbs={herbs_json_escaped};
var usage={usage_json};
var natureMap={{"寒":"寒","凉":"微寒","平":"平","温":"微温","热":"热"}};
function searchFood(){{
var kw=document.getElementById('food-keyword').value.trim().toLowerCase(),
nature=document.getElementById('food-nature').value,
meridian=document.getElementById('food-meridian').value;
var results=herbs.filter(function(h){{
if(kw){{var s=(h.name+h.effect+h.nature+h.meridian).toLowerCase();if(s.indexOf(kw)===-1)return false;}}
if(nature){{var mapped=natureMap[nature];if(h.nature!==nature&&h.nature!==mapped)return false;}}
if(meridian){{if(h.meridian.indexOf(meridian)===-1)return false;}}
return true;}});
var el=document.getElementById('food-results');
if(!results.length){{el.innerHTML='<p class="no-result">未找到匹配的食材，请调整搜索条件</p>';return;}}
var html='';
results.forEach(function(h){{var u=usage[h.name]||'可日常食用，建议根据体质适量搭配。';
html+='<div class="food-card">';
html+='<h3>'+h.name+'</h3>';
html+='<div class="meta">';
html+='<span class="tag">药性：'+h.nature+'</span>';
h.meridian.split('、').forEach(function(m){{html+='<span class="tag">归'+m+'经</span>';}});
html+='</div>';
html+='<p class="effect"><strong>功效：</strong>'+h.effect+'</p>';
html+='<div class="usage"><strong>用法建议：</strong>'+u+'</div>';
html+='<a href="{BASE_URL}/knowledge/'+h.slug+'" target="_blank">查看详细知识页 →</a>';
html+='</div>';}});
el.innerHTML=html;}}
</script>"""

    return _make_page_html(
        title=title, meta_desc=meta_desc, meta_keywords=meta_keywords,
        canonical_url=canonical, tool_name="药食同源食材查询",
        schema_json_list=[_FOOD_SCHEMA, _FOOD_FAQ_SCHEMA],
        faq_items=[
            {"question": "什么是药食同源？", "answer": "药食同源指既是食品又是中药材的物质，如山药、枸杞、红枣等。这些食材日常食用安全，同时具有调理体质功效。"},
            {"question": "药食同源食材有副作用吗？", "answer": "常规用量下安全性较高，但体质偏寒者不宜过多食用寒性食材，体质偏热者不宜过多食用温热食材。"},
            {"question": "如何根据体质选择食材？", "answer": "气虚质宜补气（黄芪、山药），阳虚质宜温补（生姜、核桃仁），阴虚质宜滋阴（百合、桑葚），痰湿质宜健脾化湿（薏苡仁、茯苓）。建议先做体质评估。"},
            {"question": "每天吃多少合适？", "answer": "一般干品10-30克/天，鲜品可适当增加。建议少量多样，长期坚持比大量短期更有效。"},
        ],
        cta_text="注册探索更多药食同源方案", cta_points="20积分",
        body_html=body,
    )


# ============================================================================
# GET 页面端点
# ============================================================================

@tools_public_router.get("/bmi-calculator", summary="BMI 计算器页面")
async def bmi_calculator_page():
    """BMI 计算器交互式页面"""
    html = _build_bmi_page()
    return HTMLResponse(
        content=html,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
    )


@tools_public_router.get("/sleep-score-calculator", summary="睡眠质量评分器页面")
async def sleep_score_calculator_page():
    """睡眠质量评分器交互式页面"""
    html = _build_sleep_page()
    return HTMLResponse(
        content=html,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
    )


@tools_public_router.get("/tcm-constitution-test", summary="中医体质自测页面")
async def tcm_constitution_test_page():
    """中医体质自测交互式页面"""
    html = _build_tcm_page()
    return HTMLResponse(
        content=html,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
    )


@tools_public_router.get("/food-medicine-query", summary="药食同源食材查询页面")
async def food_medicine_query_page():
    """药食同源食材查询交互式页面"""
    html = _build_food_page()
    return HTMLResponse(
        content=html,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
    )


# ============================================================================
# POST 数据端点 (API 访问)
# ============================================================================

@tools_public_router.post("/bmi-calculator/calculate", summary="BMI 计算器 API")
async def bmi_calculate_api(req: BMICalculateRequest):
    """BMI 计算器 JSON API 端点"""
    result = _bmi_result(req.height, req.weight, req.age, req.gender)
    return JSONResponse(
        content={"success": True, "data": result},
        headers={"Cache-Control": "public, max-age=3600"},
    )


@tools_public_router.post("/sleep-score-calculator/calculate", summary="睡眠评分 API")
async def sleep_score_calculate_api(req: SleepScoreRequest):
    """睡眠质量评分 JSON API 端点"""
    result = _sleep_result(req)
    return JSONResponse(
        content={"success": True, "data": result},
        headers={"Cache-Control": "public, max-age=3600"},
    )


@tools_public_router.post("/tcm-constitution-test/calculate", summary="体质自测 API")
async def tcm_test_calculate_api(req: TCMTestRequest):
    """中医体质自测 JSON API 端点"""
    result = _tcm_test_result(req.answers)
    return JSONResponse(
        content={"success": True, "data": result},
        headers={"Cache-Control": "public, max-age=3600"},
    )


@tools_public_router.post("/food-medicine-query/search", summary="食材查询 API")
async def food_search_api(req: FoodSearchRequest):
    """药食同源食材查询 JSON API 端点"""
    results = _food_search(
        keyword=req.keyword,
        nature=req.nature,
        meridian=req.meridian,
    )
    return JSONResponse(
        content={
            "success": True,
            "data": results,
            "total": len(results),
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )
