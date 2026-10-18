"""Configuración de la aplicación leída de variables de entorno y de config/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://srr@localhost:5433/srr"
    typesafe_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    jev_base_url: str = "https://api.typesafe.ai"
    jev_timeout_seconds: float = 15.0
    jev_max_retries: int = 2
    jev_max_concurrency: int = 4
    jev_article_budget_seconds: float = 60.0

    admin_password: str = ""
    session_secret: str = ""
    app_base_url: str = "http://localhost:8000"
    app_timezone: str = "Europe/Madrid"

    risk_policy_path: str = "config/risk_policy.json"
    rss_config_path: str = "config/rss_sources.json"
    input_manifest_path: str = "evidence/input_manifest.json"
    rss_poll_seconds: int = 300
    rss_daily_analysis_budget: int = 100
    rss_enabled: bool = True

    demo_fixtures_enabled: bool = False
    explanation_provider: str = "template"  # template | ollama | compatible
    ollama_base_url: str = ""
    ollama_model: str = ""
    generator_base_url: str = ""
    generator_api_key: str = ""
    generator_model: str = ""

    import_max_bytes: int = 10 * 1024 * 1024
    import_max_rows: int = 5000
    worker_threads: int = 4
    static_dir: str = "static"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Railway entrega postgresql://; usamos el driver psycopg 3.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def jev_configured(self) -> bool:
        return bool(self.typesafe_api_key.strip())

    @property
    def secure_cookies(self) -> bool:
        return self.app_base_url.startswith("https://")

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def file_policy() -> dict:
    return load_json(get_settings().resolve(get_settings().risk_policy_path))


@lru_cache
def location_enrichment() -> dict:
    path = get_settings().resolve("config/location_enrichment.json")
    return load_json(path) if path.is_file() else {"cities": {}, "service_scope": {}}


@lru_cache
def rss_config() -> dict:
    return load_json(get_settings().resolve(get_settings().rss_config_path))
