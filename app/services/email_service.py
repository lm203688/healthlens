"""
邮件服务 — 零外部依赖，基于 smtplib
支持 HTML 邮件模板、频率限制、异步发送
遵守中文医疗术语政策：调理/方案/分析，不使用 诊断/处方/治疗
"""
import smtplib
import threading
import time
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger

from app.config import settings

# ──────────────────────────────────────────────
# SMTP 配置（从 settings 读取，缺失则使用默认值）
# ──────────────────────────────────────────────
SMTP_HOST = settings.SMTP_HOST if hasattr(settings, "SMTP_HOST") else ""
SMTP_PORT = int(settings.SMTP_PORT) if hasattr(settings, "SMTP_PORT") else 587
SMTP_USER = settings.SMTP_USER if hasattr(settings, "SMTP_USER") else ""
SMTP_PASSWORD = settings.SMTP_PASSWORD if hasattr(settings, "SMTP_PASSWORD") else ""
SMTP_FROM = settings.SMTP_FROM if hasattr(settings, "SMTP_FROM") else "noreply@healthlens.app"
SMTP_USE_TLS = True

# ──────────────────────────────────────────────
# 频率限制：每小时最多发送 50 封
# ──────────────────────────────────────────────
_RATE_LIMIT_MAX = 50
_RATE_LIMIT_WINDOW = 3600  # 秒

_rate_lock = threading.Lock()
_rate_count = 0
_rate_window_start = 0.0


def _check_rate_limit() -> bool:
    """线程安全的频率限制检查，返回 True 表示允许发送"""
    global _rate_count, _rate_window_start
    now = time.monotonic()
    with _rate_lock:
        if now - _rate_window_start > _RATE_LIMIT_WINDOW:
            _rate_count = 0
            _rate_window_start = now
        if _rate_count >= _RATE_LIMIT_MAX:
            return False
        _rate_count += 1
        return True


# ──────────────────────────────────────────────
# 通用邮件布局骨架
# ──────────────────────────────────────────────
_EMAIL_SHELL = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f7f6;font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f7f6;padding:24px 0;">
  <tr>
    <td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

        <!-- 品牌头部 -->
        <tr>
          <td style="background-color:#0d8a6a;padding:28px 36px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;letter-spacing:1px;">
              <span style="opacity:0.85;">&#9758;</span> HealthLens
            </h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">智能健康数据管理平台</p>
          </td>
        </tr>

        <!-- 正文区域 -->
        <tr>
          <td style="padding:36px 36px 28px;color:#333333;font-size:15px;line-height:1.7;">
            {body_content}
          </td>
        </tr>

        <!-- CTA 按钮区域（可选，由模板决定是否使用） -->
        {cta_block}

        <!-- 页脚 -->
        <tr>
          <td style="background-color:#f9fafb;padding:20px 36px;border-top:1px solid #e8ecec;text-align:center;">
            <p style="margin:0;font-size:12px;color:#999999;line-height:1.6;">
              此邮件由 HealthLens 系统自动发送，请勿直接回复。<br>
              如有问题，请联系 <a href="mailto:support@healthlens.app" style="color:#0d8a6a;text-decoration:none;">support@healthlens.app</a>
            </p>
            <p style="margin:8px 0 0;font-size:11px;color:#bbbbbb;">
              &copy; {year} HealthLens. All rights reserved.
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


_CTA_BLOCK = """\
<tr>
  <td style="padding:0 36px 28px;text-align:center;">
    <a href="{cta_url}" target="_blank"
       style="display:inline-block;background-color:#0d8a6a;color:#ffffff;text-decoration:none;
              padding:14px 36px;border-radius:8px;font-size:15px;font-weight:600;
              letter-spacing:0.5px;">
      {cta_text}
    </a>
  </td>
</tr>
"""

_NO_CTA_BLOCK = ""


# ──────────────────────────────────────────────
# 内置邮件模板
# ──────────────────────────────────────────────
_TEMPLATES: dict[str, dict[str, str]] = {}

_TEMPLATES["welcome"] = {
    "subject": "欢迎加入 HealthLens — 你的健康改善之旅已开启",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">感谢你注册 <strong>HealthLens</strong> — 你的智能健康数据管理平台。我们致力于帮助你更好地了解、管理和改善个人健康。</p>
<p style="margin:0 0 16px;">以下是你开启健康之旅的几个关键步骤：</p>
<ul style="margin:0 0 16px;padding-left:20px;line-height:2;">
  <li>完善个人健康档案 — 录入基础身体数据</li>
  <li>连接智能设备 — 同步步数、心率、睡眠等数据</li>
  <li>查看健康分析 — 获取个性化的健康改善建议</li>
</ul>
<p style="margin:0 0 16px;">如有任何疑问，随时通过 App 内的帮助中心联系我们。</p>
<p style="margin:0;">祝健康！<br>HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}

_TEMPLATES["weekly_report"] = {
    "subject": "你的本周健康数据摘要",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">以下是你本周的健康数据概览：</p>
{report_summary}
<p style="margin:0 0 16px;">我们基于你的数据为你生成了个性化的健康改善建议，请登录 App 查看详细报告。</p>
<p style="margin:0;">保持健康，从每一天做起！<br>HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}

_TEMPLATES["reactivation_3d"] = {
    "subject": "你的健康数据有新变化，来看看吧",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">我们注意到你已经 <strong>{inactive_days} 天</strong>没有打开 HealthLens 了。你的健康数据仍在持续更新中，最近可能出现了一些值得关注的变化。</p>
<p style="margin:0 0 16px;">花几分钟回来看看，了解你的最新健康状况：</p>
<ul style="margin:0 0 16px;padding-left:20px;line-height:2;">
  <li>查看最新的健康指标趋势</li>
  <li>获取个性化的调理方案建议</li>
  <li>更新你的健康目标进度</li>
</ul>
<p style="margin:0;">HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}

_TEMPLATES["reactivation_7d"] = {
    "subject": "我们想念你 — 专属健康改善建议已更新",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">已经 <strong>{inactive_days} 天</strong>没有见到你了！我们为你准备了一些新的健康改善建议和数据分析，希望对你有所帮助。</p>
<p style="margin:0 0 16px;">坚持记录和追踪是改善健康的第一步，我们一直在你身边。随时回来继续你的健康之旅吧！</p>
<p style="margin:0 0 16px;">记得，持续的微小的改变会带来显著的效果。</p>
<p style="margin:0;">HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}

_TEMPLATES["points_low"] = {
    "subject": "你的健康币余额不足，来看看如何免费获取",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">你的 HealthLens 健康币余额已经不多啦。健康币可以用来解锁高级健康分析功能。</p>
<p style="margin:0 0 16px;">以下是一些免费获取健康币的方式：</p>
<ul style="margin:0 0 16px;padding-left:20px;line-height:2;">
  <li>每日签到 — 每天登录即可领取</li>
  <li>分享给好友 — 每成功邀请一位好友注册可获得奖励</li>
  <li>完善健康档案 — 录入更多健康数据获得额外奖励</li>
  <li>连续活跃 — 连续使用 App 达到指定天数可获赠</li>
</ul>
<p style="margin:0 0 16px;">快来获取更多健康币，解锁全面的健康分析服务吧！</p>
<p style="margin:0;">HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}

_TEMPLATES["share_reward"] = {
    "subject": "恭喜获得分享奖励 — 你的朋友已加入 HealthLens",
    "body": """\
<p style="margin:0 0 16px;">{user_name}，你好！</p>
<p style="margin:0 0 16px;">好消息！通过你的分享链接，你的一位好友已成功注册 HealthLens！</p>
<p style="margin:0 0 16px;">作为感谢，你已获得以下奖励：</p>
<ul style="margin:0 0 16px;padding-left:20px;line-height:2;">
  <li>健康币奖励已自动发放到你的账户</li>
  <li>解锁专属健康分析权益 7 天</li>
</ul>
<p style="margin:0 0 16px;">继续分享，让更多人关注自己的健康，你也会获得更多奖励。</p>
<p style="margin:0;">HealthLens 团队</p>
""",
    "cta_url": "",
    "cta_text": "",
}


# ──────────────────────────────────────────────
# EmailService 主类
# ──────────────────────────────────────────────
class EmailService:
    """基于 smtplib 的邮件发送服务，零外部依赖"""

    def __init__(self):
        self.host = SMTP_HOST
        self.port = SMTP_PORT
        self.user = SMTP_USER
        self.password = SMTP_PASSWORD
        self.from_addr = SMTP_FROM
        self.use_tls = SMTP_USE_TLS

        if not self.host:
            logger.warning(
                "[EmailService] SMTP_HOST 未配置，邮件发送功能将处于静默跳过模式。"
                "请在 .env 中设置 SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD 以启用。"
            )

    # ── 模板渲染 ──────────────────────────────

    @staticmethod
    def render_template(template_name: str, context: dict) -> str:
        """
        渲染邮件 HTML 模板。
        使用 Python str.format() 替换，不依赖 Jinja2。
        context 中的 key 对应模板中 {key} 占位符。
        """
        if template_name not in _TEMPLATES:
            raise ValueError(f"未知邮件模板: {template_name}，可用模板: {list(_TEMPLATES.keys())}")

        tpl = _TEMPLATES[template_name]

        # 渲染正文内容
        try:
            body_content = tpl["body"].format(**context)
        except KeyError as exc:
            raise ValueError(f"模板变量缺失: {exc}") from exc

        # 组装 CTA 按钮区块
        cta_url = tpl.get("cta_url", "")
        cta_text = tpl.get("cta_text", "")
        if cta_url and cta_text:
            cta_block = _CTA_BLOCK.format(cta_url=cta_url, cta_text=cta_text)
        else:
            cta_block = _NO_CTA_BLOCK

        # 装入通用骨架
        year = time.localtime().tm_year
        html = _EMAIL_SHELL.format(
            subject=tpl["subject"],
            body_content=body_content,
            cta_block=cta_block,
            year=year,
        )
        return html

    # ── 同步发送核心 ──────────────────────────

    def _send_sync(self, to: str, subject: str, html_body: str) -> bool:
        """
        同步发送邮件（内部方法，由 async send_email 在线程池中调用）。
        返回 True 表示发送成功。
        """
        if not self.host:
            logger.warning("[EmailService] SMTP 未配置，跳过发送: to={}", to)
            return False

        if not _check_rate_limit():
            logger.warning("[EmailService] 频率限制触发（{}/小时），跳过发送: to={}", _RATE_LIMIT_MAX, to)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = to

        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        try:
            if self.use_tls and self.port == 587:
                server = smtplib.SMTP(self.host, self.port, timeout=15)
                server.starttls()
            elif self.port == 465:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=15)

            if self.user and self.password:
                server.login(self.user, self.password)

            server.sendmail(self.from_addr, [to], msg.as_string())
            server.quit()
            logger.info("[EmailService] 邮件发送成功: to={}, subject={}", to, subject)
            return True

        except smtplib.SMTPException as exc:
            logger.error("[EmailService] SMTP 错误: to={}, error={}", to, exc)
            return False
        except Exception as exc:
            logger.error("[EmailService] 发送失败: to={}, error={}", to, exc)
            return False

    # ── 异步发送 ──────────────────────────────

    async def send_email(self, to: str, subject: str, html_body: str) -> bool:
        """
        异步发送邮件（通过线程池执行同步 SMTP 操作）。
        返回 True 表示发送成功。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._send_sync, to, subject, html_body
        )

    # ── 便捷方法 ──────────────────────────────

    async def send_welcome(self, user_email: str, user_name: str) -> bool:
        """发送注册欢迎邮件"""
        tpl = _TEMPLATES["welcome"]
        html_body = self.render_template("welcome", {"user_name": user_name})
        return await self.send_email(user_email, tpl["subject"], html_body)

    async def send_reactivation(self, user_email: str, user_name: str, inactive_days: int) -> bool:
        """
        发送未活跃唤醒邮件。
        inactive_days <= 3 使用 reactivation_3d 模板，
        inactive_days > 3 使用 reactivation_7d 模板。
        """
        if inactive_days <= 3:
            template_name = "reactivation_3d"
        else:
            template_name = "reactivation_7d"

        tpl = _TEMPLATES[template_name]
        html_body = self.render_template(template_name, {
            "user_name": user_name,
            "inactive_days": inactive_days,
        })
        return await self.send_email(user_email, tpl["subject"], html_body)

    async def send_weekly_report(self, user_email: str, user_name: str, report_data: dict) -> bool:
        """
        发送周度健康报告摘要邮件。
        report_data 应包含 key 对应模板中的变量，
        额外需要 report_summary 字段作为摘要内容。
        """
        context = {
            "user_name": user_name,
            "report_summary": report_data.get("report_summary", "<p>本周暂无数据摘要。</p>"),
        }
        # 合并 report_data 中的其他字段到 context，供自定义模板使用
        for k, v in report_data.items():
            if k not in context:
                context[k] = v

        tpl = _TEMPLATES["weekly_report"]
        html_body = self.render_template("weekly_report", context)
        return await self.send_email(user_email, tpl["subject"], html_body)

    async def send_points_low(self, user_email: str, user_name: str) -> bool:
        """发送健康币余额不足提醒"""
        tpl = _TEMPLATES["points_low"]
        html_body = self.render_template("points_low", {"user_name": user_name})
        return await self.send_email(user_email, tpl["subject"], html_body)

    async def send_share_reward(self, user_email: str, user_name: str) -> bool:
        """发送分享奖励通知"""
        tpl = _TEMPLATES["share_reward"]
        html_body = self.render_template("share_reward", {"user_name": user_name})
        return await self.send_email(user_email, tpl["subject"], html_body)
