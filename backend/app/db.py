from sqlmodel import SQLModel, create_engine

from app.config import get_env

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/goc"
DB_URL = get_env("GOC_DB_URL", DEFAULT_DB_URL) or DEFAULT_DB_URL
engine = create_engine(DB_URL, echo=False, pool_pre_ping=True)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)
