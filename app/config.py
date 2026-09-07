from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # App
    APP_NAME: str = "HealthLens"
    APP_VERSION: str = "0.22.0"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["*"]  # 生产环境应设为具体域名
    RATE_LIMIT_ENABLED: bool = True  # 认证端点限流（测试环境可禁用）
    LOG_LEVEL: str = "INFO"
    # 运行环境标识：development / staging / production
    # 生产护栏依赖它：只有 ENV=production 才会拦截 mock 验证码通道，
    # 因此本地/开发环境保持原样可用，不会误伤联调。
    ENV: str = "development"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://healthlens:healthlens@db:5432/healthlens"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "healthlens"
    MINIO_SECURE: bool = False
    
    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440    # 24h
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # FHIR
    FHIR_BASE_URL: str = ""
    
    # OCR
    OCR_ENGINE: str = "mock"  # mock / tesseract / paddleocr / smart
    OCR_LANGUAGE: str = "chi_sim+eng"
    
    # AI Model
    AI_MODEL_PATH: str = "./models"

    # Agnes AI
    AGNES_API_KEY: str = ""
    AGNES_BASE_URL: str = "https://api.agnes-ai.com/v1"

    # 通用 LLM（OpenAI 兼容协议）——可指向 DeepSeek / 通义 / OpenAI / 本地 Ollama 等
    # 优先级高于 AGNES_*，只要填了 LLM_API_KEY 就使用这一组
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # 站点主域（canonical / og:url / 分享链接统一使用，避免 SEO 权重分散）
    PUBLIC_BASE_URL: str = "https://healthlens.cc"

    
    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # 虎皮椒支付（凭证从环境变量读取，不硬编码）
    XUNHU_APPID: str = ""
    XUNHU_SECRET: str = ""
    XUNHU_GATEWAY: str = "https://api.xunhupay.com"
    XUNHU_NOTIFY_URL: str = "https://healthlens.cc/api/v1/payment/notify"
    XUNHU_RETURN_URL: str = "https://healthlens.cc/buy-points?status=success"

    # ------------------------------------------------------------------
    # Creem 国际支付（信用卡 / Merchant of Record）
    # 重要：必须使用 HealthLens **专属店铺**，不要与其他业务的店铺混用。
    #      店铺隔离可避免结算、退款、webhook 密钥与商品命名互相污染。
    # 默认关闭，配齐凭证并置 CREEM_ENABLED=true 后才对外开放。
    # ------------------------------------------------------------------
    CREEM_ENABLED: bool = False
    CREEM_API_KEY: str = ""
    CREEM_STORE_ID: str = ""          # HealthLens 专属店铺 ID（sto_ 开头）
    CREEM_WEBHOOK_SECRET: str = ""
    CREEM_BASE_URL: str = "https://api.creem.io/v1"
    CREEM_TEST_MODE: bool = False     # true 时使用 test-api.creem.io
    # 四个积分套餐对应的 Creem 产品 ID（prod_ 开头），在专属店铺内创建
    CREEM_PRODUCT_STARTER: str = ""
    CREEM_PRODUCT_BASIC: str = ""
    CREEM_PRODUCT_PRO: str = ""
    CREEM_PRODUCT_ULTIMATE: str = ""

    @property
    def creem_api_base(self) -> str:
        """按测试/生产模式返回 Creem API 基址"""
        if self.CREEM_TEST_MODE:
            return "https://test-api.creem.io/v1"
        return self.CREEM_BASE_URL

    @property
    def creem_ready(self) -> bool:
        """Creem 是否已完整配置且启用"""
        return bool(
            self.CREEM_ENABLED
            and self.CREEM_API_KEY
            and self.CREEM_STORE_ID
            and any([
                self.CREEM_PRODUCT_STARTER,
                self.CREEM_PRODUCT_BASIC,
                self.CREEM_PRODUCT_PRO,
                self.CREEM_PRODUCT_ULTIMATE,
            ])
        )

    # ------------------------------------------------------------------
    # 短信验证码（国内用户首选登录/注册方式）
    # mock 模式：仅记录日志并在响应中回传验证码，便于开发联调；
    #           生产请切到 aliyun/tencent 并设 SMS_DEV_RETURN_CODE=false。
    # ------------------------------------------------------------------
    SMS_PROVIDER: str = "mock"          # mock / aliyun / tencent
    SMS_CODE_TTL_SECONDS: int = 300     # 验证码有效期（秒）
    SMS_CODE_LENGTH: int = 6
    SMS_DEV_RETURN_CODE: bool = True     # mock 模式是否把验证码一并返回（生产务必 False）
    # 生产护栏：ENV=production 且未接入真实短信/SMTP 时，/otp/send 直接 503，
    # 绝不回显假 dev_code（那等于"无密码登录"）。默认开启，可用 false 临时放开。
    SMS_PRODUCTION_GUARD: bool = True
    SMS_RESEND_INTERVAL_SECONDS: int = 60
    # 阿里云短信（填入即用；缺省走 mock 回退并告警）
    ALIYUN_SMS_ACCESS_KEY_ID: str = ""
    ALIYUN_SMS_ACCESS_KEY_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = ""
    ALIYUN_SMS_TEMPLATE_CODE: str = ""

    # 腾讯云短信（填入即用；缺省走 mock 回退并告警）
    TENCENT_SMS_SECRET_ID: str = ""
    TENCENT_SMS_SECRET_KEY: str = ""
    TENCENT_SMS_SDK_APP_ID: str = ""
    TENCENT_SMS_SIGN_NAME: str = ""
    TENCENT_SMS_TEMPLATE_ID: str = ""

    @property
    def sms_ready(self) -> bool:
        """短信网关是否已完整配置（非 mock）"""
        if self.SMS_PROVIDER == "aliyun":
            return bool(
                self.ALIYUN_SMS_ACCESS_KEY_ID
                and self.ALIYUN_SMS_ACCESS_KEY_SECRET
                and self.ALIYUN_SMS_SIGN_NAME
                and self.ALIYUN_SMS_TEMPLATE_CODE
            )
        if self.SMS_PROVIDER == "tencent":
            return bool(
                self.TENCENT_SMS_SECRET_ID
                and self.TENCENT_SMS_SECRET_KEY
                and self.TENCENT_SMS_SDK_APP_ID
                and self.TENCENT_SMS_SIGN_NAME
                and self.TENCENT_SMS_TEMPLATE_ID
            )
        return False

    # ------------------------------------------------------------------
    # 邮箱验证码（非中国大陆用户首选登录方式；也用于欢迎信/周报等）
    # 未配置时 EmailService 静默跳过，不影响主流程。
    # ------------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@healthlens.cc"
    SMTP_USE_TLS: bool = True

    # 邮箱验证码发送上限（防止被当垃圾邮件通道滥用）
    EMAIL_CODE_MAX_PER_DAY: int = 20

    @property
    def email_ready(self) -> bool:
        """邮箱通道是否已配置"""
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    @property
    def is_production(self) -> bool:
        """是否生产环境（用于决定安全护栏是否生效）"""
        return self.ENV.strip().lower() in ("production", "prod")

    @property
    def otp_channel_live(self) -> bool:
        """是否至少有一条真实验证码通道可用（短信或邮箱）"""
        return self.sms_ready or self.email_ready

    @property
    def otp_guard_blocked(self) -> bool:
        """生产护栏是否生效：生产环境 + 未配真实通道 + 护栏开启。

        生效时 /otp/send 返回 503，而不是发一个假的 mock 验证码。
        """
        return self.is_production and self.SMS_PRODUCTION_GUARD and not self.otp_channel_live

    # ------------------------------------------------------------------
    # LLM 解析（通用 OpenAI 兼容优先，回退 Agnes）
    # ------------------------------------------------------------------

    @property
    def llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.AGNES_API_KEY

    @property
    def llm_base_url(self) -> str:
        if self.LLM_API_KEY:
            return (self.LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        return self.AGNES_BASE_URL.rstrip("/")

    @property
    def llm_model(self) -> str:
        return self.LLM_MODEL or "agnes-v1"

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key)

    # 安全默认值 (用于启动校验)
    _INSECURE_SECRETS = {"change-me-in-production", "minioadmin", "CHANGE_ME_TO_STRONG_PASSWORD", "CHANGE_ME_TO_RANDOM_64_CHAR_STRING"}

    def check_security(self) -> list[str]:
        """启动时安全检查，返回警告列表"""
        warnings = []
        if self.JWT_SECRET_KEY in self._INSECURE_SECRETS:
            warnings.append(f"JWT_SECRET_KEY 使用不安全默认值: '{self.JWT_SECRET_KEY}'")
        if self.MINIO_SECRET_KEY in self._INSECURE_SECRETS:
            warnings.append(f"MINIO_SECRET_KEY 使用不安全默认值: '{self.MINIO_SECRET_KEY}'")
        if self.CORS_ORIGINS == ["*"] and not self.DEBUG:
            warnings.append("CORS_ORIGINS=['*'] 在非调试模式下不安全")
        # 生产环境跑 mock 验证码 = 任何人凭回显码登录任意账号。
        # 无论护栏是否开启都要告警，避免"关掉护栏就忘了这件事"。
        if self.is_production and not self.otp_channel_live:
            warnings.append(
                "生产环境未配置真实短信/邮箱通道，当前验证码走 mock："
                "任何人都能凭回显码登录任意账号。请配置 ALIYUN_SMS_* / TENCENT_SMS_* / SMTP_*"
            )
        if self.otp_guard_blocked:
            warnings.append(
                f"ENV={self.ENV} 且无真实通道，/otp/send 已按 SMS_PRODUCTION_GUARD 拦截（返回 503）"
            )
        return warnings

settings = Settings()