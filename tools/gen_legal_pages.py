# -*- coding: utf-8 -*-
"""生成 HealthLens 信任/法务静态页（隐私/条款/医疗免责/数据安全/关于/联系/更新日志/帮助/API）。

设计：复用站点 design system（assets/style.css，暗色主题 + --accent #10b981），
与首页视觉一致；每个页面为独立 HTML，由 _worker.js 的 serveStatic(path+".html") 直接命中。
构建时由 build_site.py 复制到 dist/ 根目录，URL 形如 /privacy /terms /disclaimer ...
"""
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # .../healthlens
FRONTEND = ROOT / "healthlens" / "frontend"
SITE = "https://healthlens.cc"
TODAY = datetime.date.today().strftime("%Y-%m-%d")

def footer():
    return f"""
    <footer class="legal-footer">
      <div class="legal-footer-inner">
        <div class="lf-brand">
          <div class="lf-logo">HealthLens</div>
          <p>AI 驱动的健康全景平台 · 融合精准检测与食养修复</p>
        </div>
        <div class="lf-cols">
          <div>
            <h4>产品</h4>
            <a href="/">首页</a>
            <a href="/#features">功能</a>
            <a href="/changelog">更新日志</a>
            <a href="/help">帮助中心</a>
          </div>
          <div>
            <h4>法律</h4>
            <a href="/privacy">隐私政策</a>
            <a href="/terms">服务条款</a>
            <a href="/disclaimer">医疗免责声明</a>
            <a href="/security">数据安全</a>
          </div>
          <div>
            <h4>联系</h4>
            <a href="/about">关于我们</a>
            <a href="/contact">联系我们</a>
            <a href="/api-docs">API 文档</a>
          </div>
        </div>
      </div>
      <div class="lf-bottom">
        <span>© {datetime.date.today().year} HealthLens. 保留所有权利。</span>
        <span>本平台内容仅供健康科普，不构成医疗建议。</span>
      </div>
    </footer>"""

HEADER = """
    <header class="legal-header">
      <div class="legal-header-inner">
        <a class="legal-logo" href="/">
          <svg width="26" height="26" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="22" stroke="#10b981" stroke-width="2.5"/>
            <path d="M24 12v24M12 24h24" stroke="#10b981" stroke-width="2.5" stroke-linecap="round"/>
            <circle cx="24" cy="24" r="6" fill="#10b981" opacity="0.2"/>
          </svg>
          <span>HealthLens</span>
        </a>
        <a class="legal-back" href="/">返回首页 →</a>
      </div>
    </header>"""

def page(title, desc, canonical, h1, body_html):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta name="author" content="HealthLens Team">
  <link rel="canonical" href="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical}">
  <link rel="stylesheet" href="assets/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    .legal-wrap {{ max-width: 880px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }}
    .legal-header {{ position: sticky; top: 0; z-index: 20; background: var(--bg); border-bottom: 1px solid var(--border); }}
    .legal-header-inner {{ max-width: 1100px; margin: 0 auto; padding: 0.9rem 1.5rem; display: flex; align-items: center; justify-content: space-between; }}
    .legal-logo {{ display: flex; align-items: center; gap: 0.5rem; font-weight: 700; font-size: 1.15rem; color: var(--ink); text-decoration: none; }}
    .legal-back {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
    .legal-wrap h1 {{ font-size: 2rem; margin: 1rem 0 0.4rem; letter-spacing: -0.025em; }}
    .legal-updated {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }}
    .legal-wrap h2 {{ font-size: 1.3rem; margin: 2.2rem 0 0.8rem; color: var(--ink); }}
    .legal-wrap h3 {{ font-size: 1.05rem; margin: 1.4rem 0 0.5rem; color: var(--ink-secondary); }}
    .legal-wrap p, .legal-wrap li {{ color: var(--ink-secondary); line-height: 1.85; margin-bottom: 0.7rem; }}
    .legal-wrap ul {{ padding-left: 1.3rem; margin-bottom: 1rem; }}
    .legal-wrap a {{ color: var(--accent); }}
    .legal-callout {{ background: var(--accent-light); border-left: 3px solid var(--accent); padding: 1rem 1.2rem; border-radius: 0 12px 12px 0; margin: 1.2rem 0; }}
    .legal-footer {{ background: var(--dark-surface); border-top: 1px solid var(--border); margin-top: 3rem; }}
    .legal-footer-inner {{ max-width: 1100px; margin: 0 auto; padding: 2.5rem 1.5rem 1rem; display: grid; grid-template-columns: 1.4fr 2fr; gap: 2rem; }}
    .lf-logo {{ font-weight: 700; font-size: 1.2rem; color: var(--ink); margin-bottom: 0.5rem; }}
    .lf-brand p {{ color: var(--muted); font-size: 0.9rem; }}
    .lf-cols {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }}
    .lf-cols h4 {{ color: var(--ink); font-size: 0.95rem; margin-bottom: 0.8rem; }}
    .lf-cols a {{ display: block; color: var(--muted); text-decoration: none; font-size: 0.9rem; margin-bottom: 0.5rem; }}
    .lf-cols a:hover {{ color: var(--accent); }}
    .lf-bottom {{ max-width: 1100px; margin: 0 auto; padding: 1rem 1.5rem 2rem; border-top: 1px solid var(--border); display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; color: var(--muted-light); font-size: 0.82rem; }}
    @media (max-width: 760px) {{ .legal-footer-inner {{ grid-template-columns: 1fr; }} .lf-cols {{ grid-template-columns: repeat(2,1fr); }} }}
  </style>
</head>
<body>
{HEADER}
<main class="legal-wrap">
  <h1>{h1}</h1>
  <div class="legal-updated">最后更新：{TODAY}</div>
  {body_html}
</main>
{footer()}
</body>
</html>"""

PAGES = {}

PAGES["privacy"] = ("HealthLens 隐私政策", "HealthLens 如何收集、使用、存储与保护您的个人与健康数据。", f"{SITE}/privacy", "隐私政策", """
<p>本隐私政策说明 HealthLens（以下简称"我们"）在您使用网页与移动端服务时，如何收集、使用、存储与保护您的信息。使用本服务即表示您同意本政策的条款。</p>

<h2>一、我们收集的信息</h2>
<h3>1. 您主动提供的信息</h3>
<ul>
  <li><strong>账户信息</strong>：注册时提供的邮箱、登录凭证（密码经加盐哈希存储，我们无法还原明文）。</li>
  <li><strong>健康数据</strong>：您上传的体检报告、检验单、影像报告文本，以及由此生成的体质、风险与食养方案。</li>
  <li><strong>咨询内容</strong>：您与顾问、或在评估中主动填写的症状、目标与备注。</li>
</ul>
<h3>2. 自动收集的信息</h3>
<ul>
  <li>设备与网络信息（浏览器类型、访问时间、来源页），用于运维与安全防护。</li>
  <li>使用情况统计（功能点击、留存），用于改进产品。此类数据已做去标识化处理。</li>
</ul>

<h2>二、信息如何使用</h2>
<ul>
  <li>生成并展示您的个性化健康评估与食养方案；</li>
  <li>提供账户、订单与客服支持；</li>
  <li>保障服务安全，防范欺诈与滥用；</li>
  <li>在去标识化前提下，用于产品与算法的研究与改进。</li>
</ul>

<h2>三、信息共享</h2>
<p>我们<strong>不会出售</strong>您的个人健康信息。仅在以下情形向第三方提供必要数据：</p>
<ul>
  <li><strong>支付处理</strong>：订单金额与交易流水会发送至支付服务商（虎皮椒 / Creem），由其完成扣款；我们不存储您的银行卡或信用卡明文。</li>
  <li><strong>云存储与算力</strong>：报告与生成内容存储于受访问控制的对象存储与数据库，仅在为您提供服务的必要范围内处理。</li>
  <li><strong>法律要求</strong>：当法律法规或有效司法/行政机关要求时，我们可能依法披露。</li>
</ul>

<h2>四、数据存储与安全</h2>
<ul>
  <li>传输使用 TLS 加密；静态数据按敏感度分级保护。</li>
  <li>生产环境采用最小权限访问控制，操作留痕可审计。</li>
  <li>详细技术措施见 <a href="/security">数据安全</a> 页。</li>
</ul>

<h2>五、您的权利</h2>
<ul>
  <li>随时查阅、导出您本人的健康数据；</li>
  <li>要求更正不准确的信息；</li>
  <li>注销账户并请求删除您的个人数据（法律法规要求留存的除外）。</li>
</ul>
<p>行使上述权利请联系 <a href="/contact">联系我们</a>。</p>

<h2>六、未成年人</h2>
<p>本服务主要面向成年人。未成年人应在监护人知情同意下使用，监护人可代为行使上述权利。</p>

<h2>七、政策变更</h2>
<p>我们可能适时更新本政策。重大变更将通过站内通知或邮件告知，更新后的政策自发布之日起生效。</p>

<div class="legal-callout">本政策中"健康数据"为敏感个人信息。我们始终以"最小必要"为原则处理，并建议您在上传报告前隐去姓名、身份证号等直接标识符。</div>
""")

PAGES["terms"] = ("HealthLens 服务条款", "HealthLens 服务的用户协议：账户、使用规范、付费与责任边界。", f"{SITE}/terms", "服务条款", """
<p>欢迎使用 HealthLens。使用本服务前，请仔细阅读以下条款。注册或开始使用即表示您同意受本条款约束。</p>

<h2>一、服务说明</h2>
<p>HealthLens 是一个面向健康科普与个人健康管理的工具平台，提供体检数据解读、体质与风险评估、食养方案建议。本服务<strong>不构成医疗诊断、治疗或处方药建议</strong>，相关边界详见 <a href="/disclaimer">医疗免责声明</a>。</p>

<h2>二、账户</h2>
<ul>
  <li>您需对账户凭证的安全负责，并对账户下的所有活动承担责任。</li>
  <li>请使用真实有效的邮箱注册；若发现账户被盗用，请立即 <a href="/contact">联系我们</a>。</li>
</ul>

<h2>三、可接受使用</h2>
<p>您承诺不会：</p>
<ul>
  <li>上传他人健康信息而未获授权；</li>
  <li>将本服务用于临床诊疗、急诊或任何可能危害自身或他人健康的决策替代；</li>
  <li>逆向工程、攻击或干扰服务的正常运行；</li>
  <li>利用本服务从事任何违法活动。</li>
</ul>

<h2>四、付费与积分</h2>
<ul>
  <li>部分高级功能以"积分"计量，积分通过购买套餐获得。</li>
  <li>套餐价格与包含权益以 <a href="/#pricing">定价页</a> 实时展示为准。</li>
  <li>已消耗的分析积分原则上不予退款；未使用套餐在法定情形下可依据消费者权益规定处理。</li>
</ul>

<h2>五、知识产权</h2>
<p>本平台的软件、设计、内容与算法均归 HealthLens 或相关权利人所有。您生成的健康方案仅供您个人使用，未经许可不得大规模复制、转售或用于商业培训。</p>

<h2>六、责任限制</h2>
<p>在适用法律允许的最大范围内，对于因使用或无法使用本服务导致的间接、偶然或后果性损害，我们不承担法律责任。我们的总赔偿责任以您在该期间内实际支付的费用为上限。</p>

<h2>七、条款变更与终止</h2>
<p>我们可因业务调整更新本条款，并通过适当方式通知。若您继续使用即视为接受变更；您也可随时停止使用并注销账户。</p>

<h2>八、适用法律</h2>
<p>本条款适用中华人民共和国法律。争议优先通过友好协商解决。</p>
""")

PAGES["disclaimer"] = ("HealthLens 医疗免责声明", "重要：HealthLens 不是医疗器械，所有输出仅供参考，不构成诊疗建议。", f"{SITE}/disclaimer", "医疗免责声明", """
<div class="legal-callout"><strong>请先阅读：</strong>HealthLens 是健康科普与自我管理工具，<strong>不是医疗器械，也不提供医疗诊断、治疗或处方服务</strong>。本页内容具有约束力，使用本服务即表示您理解并同意以下声明。</div>

<h2>一、非诊疗性质</h2>
<ul>
  <li>本平台基于您上传的体检/检验数据，结合公开文献与知识库给出<strong>参考性</strong>的归因分析与生活方式建议。</li>
  <li>平台输出<strong>不能替代</strong>执业医师、营养师或药师的面诊、诊断与治疗方案。</li>
  <li>若您正在接受疾病治疗或服用处方药，请务必以您主治医生的意见为准。</li>
</ul>

<h2>二、AI 生成内容的局限</h2>
<ul>
  <li>系统输出由算法生成，可能存在误差、遗漏或时效性偏差；个别指标解读需结合完整临床背景。</li>
  <li>基因与多组学数据的解释具有概率性与不确定性，不应被理解为"确诊"或"预后预测"。</li>
</ul>

<h2>三、紧急情况</h2>
<p>如出现胸痛、呼吸困难、意识改变、急性出血等<strong>急症征象</strong>，请立即就医或拨打急救电话，<strong>切勿</strong>依赖本平台判断延误治疗。</p>

<h2>四、药食相互作用提示</h2>
<p>食养方案涉及的草本与营养素可能与药物发生相互作用，例如：</p>
<ul>
  <li>当归、银杏等可能影响凝血，与华法林同用需谨慎；</li>
  <li>圣约翰草（贯叶连翘）会降低多种处方药疗效；</li>
  <li>高剂量钙/铁补充剂可能影响部分抗生素吸收。</li>
</ul>
<p>在开始任何膳食补充前，请与您的医师或药师确认兼容性。</p>

<h2>五、数据与个体差异</h2>
<p>健康建议基于群体证据与您的输入数据推演，无法覆盖全部个体变量（基因型、合并用药、生活环境等）。请结合自身情况审慎采纳。</p>

<h2>六、责任边界</h2>
<p>在适用法律允许范围内，HealthLens 不对因依赖本平台内容产生的任何健康后果承担责任。您对自身健康决策负最终责任。</p>
""")

PAGES["security"] = ("HealthLens 数据安全", "HealthLens 如何在传输、存储与访问控制层面保护您的健康数据。", f"{SITE}/security", "数据安全", """
<p>健康数据是高度敏感的信息。我们以"默认安全"为原则，从基础设施到应用层构建防护。</p>

<h2>一、传输与存储加密</h2>
<ul>
  <li><strong>传输层</strong>：全站强制 TLS（HTTPS），前端与后端通信加密。</li>
  <li><strong>存储层</strong>：健康内容按敏感度分级，静态数据加密存储；密码使用加盐哈希，无法还原明文。</li>
  <li><strong>密钥管理</strong>：凭据与密钥隔离存储，不进入代码仓库。</li>
</ul>

<h2>二、基础设施</h2>
<ul>
  <li>后端服务运行于受访问控制的云主机，数据库与对象存储均启用访问控制与网络隔离。</li>
  <li>生产环境采用最小权限原则，人员操作留痕、可审计。</li>
  <li>定期更新与补丁管理，降低已知漏洞风险。</li>
</ul>

<h2>三、访问控制</h2>
<ul>
  <li>您的账户数据仅您本人（及您授权的顾问）可访问。</li>
  <li>内部运维访问受角色权限约束，并受监控。</li>
</ul>

<h2>四、支付安全</h2>
<ul>
  <li>支付由持牌支付机构（虎皮椒 / Creem）处理，我们不存储银行卡或信用卡明文。</li>
  <li>交易数据传输符合对应支付机构的合规要求。</li>
</ul>

<h2>五、事件响应</h2>
<p>若发生数据安全事件，我们将依照法律法规要求及时采取处置措施，并在适用情形下通知受影响用户与监管机构。</p>

<h2>六、您的责任</h2>
<ul>
  <li>请使用强密码并妥善保管账户凭证；</li>
  <li>上传报告前建议隐去姓名、证件号等直接标识符；</li>
  <li>不在公共设备保持登录状态，离开时请退出。</li>
</ul>

<div class="legal-callout">我们持续改进安全实践，但没有任何系统能做到绝对安全。如发现漏洞，请通过 <a href="/contact">联系我们</a> 渠道反馈，我们诚挚感谢负责任的披露。</div>
""")

PAGES["about"] = ("关于 HealthLens", "HealthLens 的理念：从指标异常到细胞机制再到食养修复的完整因果链。", f"{SITE}/about", "关于我们", """
<p>HealthLens 致力于把"复杂但可解释"的健康知识，变成普通人用得上的日常工具。</p>

<h2>我们解决的问题</h2>
<p>一次体检往往产生几十项异常箭头，但很少有人能说清：这些指标彼此如何关联、背后是什么生理机制、又能从饮食与作息上做哪些温和干预。HealthLens 把这条因果链补全：</p>
<ul>
  <li><strong>指标解读</strong>：把异常值翻译成易懂的机制说明；</li>
  <li><strong>归因分析</strong>：从生化通路、细胞层面解释"为什么会这样"；</li>
  <li><strong>中医映射</strong>：将现代指标与传统体质证候关联，提供可执行的食养方案；</li>
  <li><strong>风险分层</strong>：提示哪些问题值得优先关注、哪些可以先观察。</li>
</ul>

<h2>我们的立场</h2>
<ul>
  <li>多数亚健康问题应<strong>先用饮食与作息干预，而非直接用药</strong>；</li>
  <li>所有建议必须<strong>有文献或机制依据</strong>，不夸大、不制造焦虑；</li>
  <li>健康数据属于用户本人，我们以最小必要原则处理。</li>
</ul>

<h2>我们不是什么</h2>
<p>HealthLens <strong>不是医院、不是诊所、不提供诊断或处方</strong>。我们是与您和您的医生协作的"第二双眼睛"，最终决策权在您和您的医疗团队手中。详见 <a href="/disclaimer">医疗免责声明</a>。</p>

<h2>联系</h2>
<p>合作、媒体或问题反馈，欢迎通过 <a href="/contact">联系我们</a> 与我们沟通。</p>
""")

PAGES["contact"] = ("联系我们 - HealthLens", "HealthLens 的联系方式、响应时间与问题反馈渠道。", f"{SITE}/contact", "联系我们", """
<p>我们重视每一次反馈。以下方式均可联系到 HealthLens 团队。</p>

<h2>一般咨询与合作</h2>
<ul>
  <li>邮箱：<a href="mailto:hello@healthlens.cc">hello@healthlens.cc</a></li>
  <li>商务合作：同上邮箱，标题请注明"合作"。</li>
</ul>

<h2>问题反馈与故障申报</h2>
<ul>
  <li>功能异常、数据错误、页面问题：请附上截图与复现步骤，发送至上述邮箱；</li>
  <li>安全漏洞：欢迎负责任的披露，我们将尽快响应并致谢。</li>
</ul>

<h2>响应时间</h2>
<ul>
  <li>账户与订单类：1–2 个工作日内；</li>
  <li>一般咨询：3 个工作日内；</li>
  <li>安全事件：按漏洞等级优先处理。</li>
</ul>

<h2>用户支持范围说明</h2>
<p>我们可提供产品使用、账户与数据相关的支持；但<strong>不提供医疗问诊</strong>，相关健康问题请遵医嘱。涉及诊断与治疗，请前往正规医疗机构。</p>

<div class="legal-callout">当前为自动化支持通道，人工将于上述时限内回复。紧急情况请直接就医。</div>
""")

PAGES["changelog"] = ("HealthLens 更新日志", "HealthLens 近期产品与内容迭代记录。", f"{SITE}/changelog", "更新日志", """
<p>我们持续迭代产品与内容。以下为近期主要更新（按时间倒序）。</p>

<h2>2026-08</h2>
<ul>
  <li>统一全站品牌与域名（healthlens.cc），补全隐私、条款、医疗免责与数据安全等信任页面；</li>
  <li>优化 SEO 长尾内容结构与站点地图，提升可发现性；</li>
  <li>后端健康检查与任务队列稳定性加固。</li>
</ul>

<h2>2026-07</h2>
<ul>
  <li>上线体检报告解读与五层因果链分析；</li>
  <li>接入中医体质与食养方案推荐；</li>
  <li>开通积分套餐与支付通道。</li>
</ul>

<h2>更早</h2>
<ul>
  <li>完成 MVP 与首批健康知识库内容建设。</li>
</ul>

<p class="legal-updated">更新记录仅节选主要节点，更多细节以实际产品为准。</p>
""")

PAGES["help"] = ("HealthLens 帮助中心", "HealthLens 使用常见问题：报告上传、积分、数据安全与结果解读。", f"{SITE}/help", "帮助中心", """
<h2>如何开始？</h2>
<ol>
  <li>在首页点击"免费注册"创建账户；</li>
  <li>上传一份体检报告（PDF 或文本均可），系统将解析指标；</li>
  <li>查看您的健康评估、体质倾向与食养方案。</li>
</ol>

<h2>支持哪些报告？</h2>
<ul>
  <li>常规体检、检验单（血常规、生化、激素等）、部分影像报告文本；</li>
  <li>基因/多组学报告的解读能力正在完善中。</li>
</ul>

<h2>积分与套餐</h2>
<ul>
  <li>每次完整分析消耗一定积分，积分通过购买套餐获得；</li>
  <li>套餐详情见 <a href="/#pricing">定价页</a>。</li>
</ul>

<h2>我的数据安全吗？</h2>
<p>我们采用传输与存储加密、最小权限访问控制，且不出售您的健康信息。详见 <a href="/security">数据安全</a> 与 <a href="/privacy">隐私政策</a>。</p>

<h2>结果看不懂 / 有疑问？</h2>
<ul>
  <li>每条建议都附带机制说明，可展开查看；</li>
  <li>涉及诊断或用药，请遵医嘱，本平台<strong>不构成医疗建议</strong>（<a href="/disclaimer">免责声明</a>）。</li>
</ul>

<h2>更多帮助</h2>
<p>未涵盖的问题，欢迎通过 <a href="/contact">联系我们</a> 反馈。</p>
""")

PAGES["api-docs"] = ("HealthLens API 文档", "HealthLens 后端 API 概览与接入说明。", f"{SITE}/api-docs", "API 文档", """
<p>HealthLens 后端提供一套以 RESTful 风格组织的 API，供前端与授权合作伙伴调用。以下内容为概览，完整规范以实际接口为准。</p>

<h2>基础信息</h2>
<ul>
  <li>Base URL：<code>https://api.healthlens.cc</code></li>
  <li>认证：Bearer Token（登录后由前端持有，不在客户端明文存储）；</li>
  <li>内容类型：<code>application/json</code>。</li>
</ul>

<h2>主要资源</h2>
<ul>
  <li><code>POST /api/v1/auth/register|login</code> — 账户与鉴权；</li>
  <li><code>POST /api/v1/reports/upload</code> — 上传并解析体检报告；</li>
  <li><code>GET  /api/v1/analysis/...</code> — 获取指标解读、体质与食养方案；</li>
  <li><code>GET  /api/v1/growth/points/packages</code> — 积分套餐列表；</li>
  <li><code>POST /api/v1/growth/points/buy</code> — 创建购买订单（转发支付网关）。</li>
</ul>

<h2>接入与授权</h2>
<p>公开 API 当前主要服务于官方前端。第三方集成、合作伙伴或研究用途，请通过 <a href="/contact">联系我们</a> 申请授权与密钥，我们按场景评估开放范围。</p>

<div class="legal-callout">调用频率受限流策略约束；滥用可能导致令牌失效。请勿在客户端代码中硬编码任何密钥。</div>
""")

def build():
    out = FRONTEND
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for slug, (title, desc, canon, h1, body) in PAGES.items():
        html = page(title, desc, canon, h1, body)
        p = out / f"{slug}.html"
        p.write_text(html, encoding="utf-8")
        count += 1
        print(f"  {slug}.html  ({len(html)//1024} KB)")
    print(f"generated {count} legal/trust pages in {FRONTEND}")

if __name__ == "__main__":
    build()
