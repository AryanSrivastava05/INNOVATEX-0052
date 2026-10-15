from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tick_seconds: int = 5
    webhook_url: str = ""
    frontend_origin: str = "http://localhost:3000"
    escalation_seconds: int = 60
    demo_token: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = 10.0
    stale_seconds: int = 30
    trend_window: int = 5
    spo2_warning: int = 92
    spo2_critical: int = 90
    heart_rate_warning_high: int = 110
    heart_rate_warning_low: int = 50
    heart_rate_critical_high: int = 130
    heart_rate_critical_low: int = 40
    systolic_bp_warning_high: int = 160
    systolic_bp_warning_low: int = 95
    systolic_bp_critical_high: int = 180
    systolic_bp_critical_low: int = 85


settings = Settings()
