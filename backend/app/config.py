from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_secret: str = "dev-secret"
    openai_api_key: str | None = None
    database_url: str = "sqlite:///./rag_platform.db"
    rate_limit_per_minute: int = 120
    frontend_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "https://enterprise-rag-platform-coral.vercel.app"
    )
    frontend_origin_regex: str | None = r"https://.*\.vercel\.app"

    class Config:
        env_file = ".env"


settings = Settings()
