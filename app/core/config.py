
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root: indian-ecommerce-support-chatbot/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "Indian E-commerce Support Chatbot"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str

    # Ollama configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "qwen2.5:1.5b"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Document configuration
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 20
    TOP_K: int = 5

    # Application security
    APP_SECRET_KEY: str

    # Gmail SMTP configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    # Administrator configuration
    ADMIN_USERNAME: str
    ADMIN_EMAIL: str
    ADMIN_PASSWORD_HASH: str

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
