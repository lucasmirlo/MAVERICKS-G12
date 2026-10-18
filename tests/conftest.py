import os

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://srr@localhost:5433/srr_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["TYPESAFE_API_KEY"] = "test-key-not-real"
os.environ["ADMIN_PASSWORD"] = "test-presenter-password"
os.environ["SESSION_SECRET"] = "test-session-secret-0123456789"
os.environ["DEMO_FIXTURES_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "none"  # las pruebas nunca llaman a un LLM real
os.environ["APP_BASE_URL"] = "http://testserver"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import ROOT, get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def migrated():
    url = get_settings().sqlalchemy_url
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    eng.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    yield


TABLES = ["alerts", "incident_articles", "incidents", "supplier_assessments", "analyses", "jev_calls", "evaluation_runs",
          "evaluation_labels", "drafts", "jobs", "article_versions", "articles", "import_batches", "material_products",
          "materials", "suppliers", "sources", "policy_versions", "app_state"]


@pytest.fixture()
def db(migrated):
    from app.db import SessionLocal, engine
    from app.policy import ensure_seeded

    with engine().begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES) + " CASCADE"))
    session = SessionLocal()
    ensure_seeded(session)
    yield session
    session.close()
