from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./certificates.sqlite"
    storage_dir: str = "./storage"
    max_batch_size: int = 1000
    api_key: str = "dev-secret-key-12345"
    api_key_name: str = "X-API-Key"
    rate_limit_jobs: str = "5/minute"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    cert_max_retries: int = 3
    cert_retry_backoff_base: float = 0.5
    storage_type: str = "local"
    s3_bucket_name: str = "certificates"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    log_level: str = "INFO"
    
    # Email / SMTP Configuration
    email_enabled: bool = False
    smtp_host: str = "smtp.sendgrid.net"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    email_from: str = "certificates@example.com"
    email_from_name: str = "CertifyFlow"

    
    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
