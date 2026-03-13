import sys
from functools import lru_cache
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    github_token: str
    github_webhook_secret: str
    anthropic_api_key: str
    log_level: str = "INFO"


@lru_cache()
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        print("\n" + "=" * 80, file=sys.stderr)
        print("❌ CONFIGURATION ERROR: Missing required environment variables", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("\nThe following environment variables are required but not set:\n", file=sys.stderr)
        
        for error in e.errors():
            field_name = error["loc"][0]
            print(f"  ❌ {field_name.upper()}", file=sys.stderr)
        
        print("\n📝 Setup instructions:", file=sys.stderr)
        print("  1. Copy the template:     cp .env.example .env", file=sys.stderr)
        print("  2. Edit .env with your actual tokens:", file=sys.stderr)
        print("     - GITHUB_TOKEN: https://github.com/settings/tokens", file=sys.stderr)
        print("     - GITHUB_WEBHOOK_SECRET: openssl rand -hex 32", file=sys.stderr)
        print("     - ANTHROPIC_API_KEY: https://console.anthropic.com", file=sys.stderr)
        print("=" * 80 + "\n", file=sys.stderr)
        raise


settings = get_settings()


def _setup_logging():
    from src.utils.logger import setup_logger
    setup_logger(level=settings.log_level)


_setup_logging()
