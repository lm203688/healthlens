from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # App
    APP_NAME: str = "HealthLens"
    APP_VERSION: str = "0.8.2"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["*"]  # 生产环境应设为具体域名
    
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
    
    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

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
        return warnings

settings = Settings()