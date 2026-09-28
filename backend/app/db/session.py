from collections.abc import Iterator

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import get_settings

settings = get_settings()


def _engine_url(value: str) -> URL:
    database_url = make_url(value)
    if database_url.drivername in {"postgres", "postgresql"}:
        database_url = database_url.set(drivername="postgresql+psycopg")
    return database_url


database_url = _engine_url(settings.database_url)
_is_sqlite = database_url.get_backend_name() == "sqlite"

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # enforce foreign keys in SQLite
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
