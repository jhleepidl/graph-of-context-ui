import atexit
import logging
import re
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlmodel import SQLModel, Session, create_engine

from app.config import get_env
from app.models import ConversationTeamConfig, MemoryNode, MemoryProjection, MemorySurface, ServiceRequest, Thread
from app.services.agent_defaults import ensure_default_agents

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/goc"
_POSTGRES_SCHEMES = ("postgres://", "postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")
_SQLITE_SCHEMES = ("sqlite://", "sqlite+pysqlite://")
_SAFE_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,62}$")
logger = logging.getLogger(__name__)


def normalize_db_url(db_url: str | None) -> str:
    if db_url is None:
        raw = DEFAULT_DB_URL
    else:
        raw = str(db_url).strip()
        if not raw:
            return ""
    if raw.startswith("postgres://"):
        return "postgresql+psycopg2://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg2://" + raw[len("postgresql://") :]
    return raw


def is_sqlite_url(db_url: str | None) -> bool:
    return normalize_db_url(db_url).startswith(_SQLITE_SCHEMES)


def is_postgres_url(db_url: str | None) -> bool:
    return normalize_db_url(db_url).startswith(_POSTGRES_SCHEMES)


def build_engine(db_url: str | None = None) -> Engine:
    normalized = normalize_db_url(db_url)
    engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if is_sqlite_url(normalized):
        engine_kwargs.update({"connect_args": {"check_same_thread": False}})
    return create_engine(normalized, **engine_kwargs)


def _should_auto_create_database() -> bool:
    raw = str(get_env("GOC_DB_AUTO_CREATE", "false") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _derive_postgres_admin_db_url(db_url: str) -> str | None:
    normalized = normalize_db_url(db_url)
    if not is_postgres_url(normalized):
        return None
    explicit_raw = str(get_env("GOC_DB_CREATE_URL", "") or "").strip()
    if explicit_raw:
        return normalize_db_url(explicit_raw)
    url = make_url(normalized)
    admin_db = str(get_env("GOC_DB_CREATE_DATABASE", "postgres") or "postgres").strip() or "postgres"
    return url.set(database=admin_db).render_as_string(hide_password=False)


def _safe_postgres_database_name(db_url: str) -> str | None:
    try:
        database = str(make_url(normalize_db_url(db_url)).database or "").strip()
    except Exception:
        return None
    if not database or not _SAFE_DB_NAME_RE.match(database):
        return None
    return database


def ensure_database_exists(db_url: str | None = None) -> None:
    normalized = normalize_db_url(db_url)
    if not _should_auto_create_database() or not is_postgres_url(normalized):
        return

    target_db = _safe_postgres_database_name(normalized)
    admin_db_url = _derive_postgres_admin_db_url(normalized)
    if not target_db or not admin_db_url:
        logger.warning("skipping postgres auto-create because database name or admin url is invalid")
        return

    admin_engine = create_engine(admin_db_url, echo=False, pool_pre_ping=True, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": target_db},
            ).scalar()
            if exists:
                return
            conn.execute(text(f'CREATE DATABASE "{target_db}"'))
            logger.info("created postgres database '%s'", target_db)
    finally:
        admin_engine.dispose()


DB_URL = normalize_db_url(get_env("GOC_DB_URL", DEFAULT_DB_URL)) or DEFAULT_DB_URL
engine = build_engine(DB_URL)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def dispose_engine() -> None:
    try:
        engine.dispose()
    except Exception:
        logger.exception("failed to dispose database engine")


def ping_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("database ping failed")
        return False


def _ensure_thread_columns() -> None:
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

        if "external_ref" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN external_ref VARCHAR(255)"))
            cols.add("external_ref")
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_external_ref ON {table_name} (external_ref)"))
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_service_id_external_ref "
                f"ON {table_name} (service_id, external_ref)"
            )
        )

        if "meta_json" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN meta_json TEXT DEFAULT '{{}}'"))
            cols.add("meta_json")
        conn.execute(text(f"UPDATE {table_name} SET meta_json = '{{}}' WHERE meta_json IS NULL"))


def _ensure_service_request_columns() -> None:
    table_name = getattr(ServiceRequest, "__tablename__", "servicerequest")
    with engine.begin() as conn:
        inspector = inspect(conn)
        if table_name not in inspector.get_table_names():
            return
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        if "description" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN description TEXT"))


def _ensure_conversation_team_config_columns() -> None:
    table_name = getattr(ConversationTeamConfig, "__tablename__", "conversation_team_configs")
    with engine.begin() as conn:
        inspector = inspect(conn)
        if table_name not in inspector.get_table_names():
            return
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        if "state_json" not in cols:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN state_json TEXT DEFAULT '{{}}'"))
            cols.add("state_json")
        conn.execute(text(f"UPDATE {table_name} SET state_json = '{{}}' WHERE state_json IS NULL"))




def _add_column_if_missing(conn, table_name: str, cols: set[str], column_name: str, ddl: str) -> None:
    if column_name in cols:
        return
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    cols.add(column_name)


def _ensure_memory_graph_columns() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())

        surface_table = getattr(MemorySurface, "__tablename__", "memory_surfaces")
        if surface_table in tables:
            cols = {c["name"] for c in inspector.get_columns(surface_table)}
            _add_column_if_missing(conn, surface_table, cols, "title", "TEXT DEFAULT ''")
            _add_column_if_missing(conn, surface_table, cols, "semantic_kind", "VARCHAR(255) DEFAULT 'generic'")
            _add_column_if_missing(conn, surface_table, cols, "visibility_scope", "VARCHAR(255) DEFAULT 'shared'")
            _add_column_if_missing(conn, surface_table, cols, "write_mode", "VARCHAR(255) DEFAULT 'shared'")
            _add_column_if_missing(conn, surface_table, cols, "policy_json", "TEXT DEFAULT '{}'")
            _add_column_if_missing(conn, surface_table, cols, "created_at", "TIMESTAMP")
            _add_column_if_missing(conn, surface_table, cols, "updated_at", "TIMESTAMP")
            conn.execute(text(f"UPDATE {surface_table} SET title = '' WHERE title IS NULL"))
            conn.execute(text(f"UPDATE {surface_table} SET semantic_kind = 'generic' WHERE semantic_kind IS NULL"))
            conn.execute(text(f"UPDATE {surface_table} SET visibility_scope = 'shared' WHERE visibility_scope IS NULL"))
            conn.execute(text(f"UPDATE {surface_table} SET write_mode = 'shared' WHERE write_mode IS NULL"))
            conn.execute(text(f"UPDATE {surface_table} SET policy_json = '{{}}' WHERE policy_json IS NULL"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{surface_table}_thread_id ON {surface_table} (thread_id)"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{surface_table}_surface_id ON {surface_table} (surface_id)"))

        node_table = getattr(MemoryNode, "__tablename__", "memory_nodes")
        if node_table in tables:
            cols = {c["name"] for c in inspector.get_columns(node_table)}
            _add_column_if_missing(conn, node_table, cols, "node_type", "VARCHAR(255) DEFAULT 'note'")
            _add_column_if_missing(conn, node_table, cols, "owner_agent_id", "VARCHAR(255)")
            _add_column_if_missing(conn, node_table, cols, "owner_role_id", "VARCHAR(255)")
            _add_column_if_missing(conn, node_table, cols, "content_json", "TEXT DEFAULT '{}'")
            _add_column_if_missing(conn, node_table, cols, "provenance_json", "TEXT DEFAULT '{}'")
            _add_column_if_missing(conn, node_table, cols, "trust_tier", "VARCHAR(255) DEFAULT 'derived'")
            _add_column_if_missing(conn, node_table, cols, "status", "VARCHAR(255) DEFAULT 'draft'")
            _add_column_if_missing(conn, node_table, cols, "created_run_id", "VARCHAR(255)")
            _add_column_if_missing(conn, node_table, cols, "created_at", "TIMESTAMP")
            _add_column_if_missing(conn, node_table, cols, "updated_at", "TIMESTAMP")
            conn.execute(text(f"UPDATE {node_table} SET node_type = 'note' WHERE node_type IS NULL"))
            conn.execute(text(f"UPDATE {node_table} SET content_json = '{{}}' WHERE content_json IS NULL"))
            conn.execute(text(f"UPDATE {node_table} SET provenance_json = '{{}}' WHERE provenance_json IS NULL"))
            conn.execute(text(f"UPDATE {node_table} SET trust_tier = 'derived' WHERE trust_tier IS NULL"))
            conn.execute(text(f"UPDATE {node_table} SET status = 'draft' WHERE status IS NULL"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{node_table}_thread_id ON {node_table} (thread_id)"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{node_table}_surface_id ON {node_table} (surface_id)"))

        projection_table = getattr(MemoryProjection, "__tablename__", "memory_projections")
        if projection_table in tables:
            cols = {c["name"] for c in inspector.get_columns(projection_table)}
            _add_column_if_missing(conn, projection_table, cols, "run_id", "VARCHAR(255)")
            _add_column_if_missing(conn, projection_table, cols, "agent_id", "VARCHAR(255)")
            _add_column_if_missing(conn, projection_table, cols, "role_id", "VARCHAR(255)")
            _add_column_if_missing(conn, projection_table, cols, "visible_node_ids_json", "TEXT DEFAULT '[]'")
            _add_column_if_missing(conn, projection_table, cols, "blocked_node_ids_json", "TEXT DEFAULT '[]'")
            _add_column_if_missing(conn, projection_table, cols, "summary_json", "TEXT DEFAULT '{}'")
            _add_column_if_missing(conn, projection_table, cols, "budget_tokens", "INTEGER DEFAULT 0")
            _add_column_if_missing(conn, projection_table, cols, "compiled_tokens_estimate", "INTEGER DEFAULT 0")
            _add_column_if_missing(conn, projection_table, cols, "created_at", "TIMESTAMP")
            _add_column_if_missing(conn, projection_table, cols, "updated_at", "TIMESTAMP")
            conn.execute(text(f"UPDATE {projection_table} SET visible_node_ids_json = '[]' WHERE visible_node_ids_json IS NULL"))
            conn.execute(text(f"UPDATE {projection_table} SET blocked_node_ids_json = '[]' WHERE blocked_node_ids_json IS NULL"))
            conn.execute(text(f"UPDATE {projection_table} SET summary_json = '{{}}' WHERE summary_json IS NULL"))
def init_db() -> None:
    ensure_database_exists(DB_URL)
    SQLModel.metadata.create_all(engine)
    _ensure_thread_columns()
    _ensure_service_request_columns()
    _ensure_conversation_team_config_columns()
    _ensure_memory_graph_columns()
    try:
        with session_scope() as session:
            ensure_default_agents(session)
            session.commit()
    except Exception:
        logger.exception("default agent seed failed during init_db")


atexit.register(dispose_engine)
