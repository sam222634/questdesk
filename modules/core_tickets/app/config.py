from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tickets_admin:tickets_local_dev@db:5432/tickets_core"
    bitacoras_dir: Path = Path("/data/bitacoras")
    default_api_key: str = "questdesk-local-dev-key"
    app_title: str = "QuestDesk - Core Ticketing Service"
    app_version: str = "0.2.0"
    questdesk_mode: str = "enterprise"


settings = Settings()
