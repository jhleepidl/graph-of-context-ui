from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

from app.config import get_env
from app.models import ServiceRequest, Thread

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/goc"
DB_URL = get_env("GOC_DB_URL", DEFAULT_DB_URL) or DEFAULT_DB_URL
engine = create_engine(DB_URL, echo=False, pool_pre_ping=True)


def _ensure_thread_service_column() -> None:
    table_name = getattr(Thread, "__tablename__", "thread")
    with engine.begin() as conn:
        inspector = inspect(conn)
        if table_name not in inspector.get_table_names():
            return

        cols = {c["name"] for c in inspector.get_columns(table_name)}
        if "service_id" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN service_id VARCHAR(255)"))
            cols.add("service_id")

        if "tenant_id" in cols:
            conn.execute(
                text(
                    f"UPDATE {table_name} "
                    "SET service_id = tenant_id "
                    "WHERE service_id IS NULL AND tenant_id IS NOT NULL"
                )
            )
        conn.execute(text(f"UPDATE {table_name} SET service_id = 'default' WHERE service_id IS NULL"))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_service_id ON {table_name} (service_id)"))


def _ensure_service_request_columns() -> None:
    table_name = getattr(ServiceRequest, "__tablename__", "servicerequest")
    with engine.begin() as conn:
        inspector = inspect(conn)
        if table_name not in inspector.get_table_names():
            return
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        if "description" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN description TEXT"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_thread_service_column()
    _ensure_service_request_columns()
