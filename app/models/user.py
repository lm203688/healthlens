from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        default="patient",
        server_default="patient",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    nickname: Mapped[str | None] = mapped_column(String(100))
    # UTM 来源追踪（注册时写入）
    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(200))
    referral_code: Mapped[str | None] = mapped_column(String(50))

    # ------------------------------------------------------------------
    # 区域标识（数据驻留 + Claims 策略路由的地基）
    # region：数据平面部署区域（"cn"=中国内地 / "sg"=新加坡亚太 / "eu"=EU 等），
    #         决定该用户 PII 存放在哪个物理部署。跨区域读写 PII 在代码层强制拦截。
    # jurisdiction：Claims/合规策略所属法域，用于输出前按 jurisdiction 过滤字段。
    # 两者关系：jurisdiction 通常 == region，但当同一部署服务多法域时（如 EU 部署
    # 服务 EU+UK 客户），jurisdiction 由用户显式选择，region 保持部署区域不变。
    # 默认 cn 兼容既有用户（PIPL 是本项目首发法域）。
    # ------------------------------------------------------------------
    region: Mapped[str] = mapped_column(
        String(8), default="cn", server_default="cn", nullable=False
    )
    jurisdiction: Mapped[str] = mapped_column(
        String(8), default="cn", server_default="cn", nullable=False
    )

    # TOTP（认证器 App，零外部依赖的验证码通道）
    # totp_secret 为 base32 编码的随机密钥，仅登录校验用，不用于其他鉴权。
    # 明文存储系最小实现；如需更强保护可在写入前用 SMTP_FROM 派生密钥做 AES 加密。
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    # 首选验证码通道：otp（短信/邮件二选一，由账号类型决定）/ totp（认证器）
    otp_method: Mapped[str] = mapped_column(
        String(10), default="otp", server_default="otp"
    )