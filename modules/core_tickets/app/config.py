from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tickets_admin:tickets_local_dev@db:5432/tickets_core"
    bitacoras_dir: Path = Path("/data/bitacoras")
    app_title: str = "QuestDesk - Core Ticketing Service"
    app_version: str = "0.1.0"


settings = Settings()
