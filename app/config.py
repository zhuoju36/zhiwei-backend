"""集中管理环境变量配置（Pydantic Settings）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库
    database_url: str = "postgresql+asyncpg://shm_user:shm_pass@localhost:5432/shm_db"
    timescale_enabled: bool = True

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "shm-storage"

    # 安全
    secret_key: str = "dev-only-secret-key-change-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # 边缘网关接入
    edge_api_key: str = "edge-secret-key"

    # DTU 监听接入（v0.9，app/dtu_server 独立进程）
    dtu_batch_size: int = 100  # 攒批条数
    dtu_flush_interval_s: float = 0.5  # 攒批最大等待秒数

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 告警通知（v0.5）：全部可选；配置则启用对应通道
    # Webhook 通道
    webhook_url: str = ""  # 例如 https://oapi.dingtalk.com/robot/send?access_token=...
    webhook_headers: str = ""  # JSON 字符串，如 '{"X-Custom":"v"}'
    webhook_timeout_seconds: float = 10.0
    # Email 通道（SMTP）
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from: str = ""
    alert_email_to: str = ""  # 逗号分隔

    # CORS（生产环境禁止使用 "*"）
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def asyncpg_dsn(self) -> str:
        """将 SQLAlchemy 风格的 URL 转为 asyncpg 原生 DSN。"""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


settings = Settings()
