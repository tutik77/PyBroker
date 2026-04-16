from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        echo=settings.echo_sql,
        pool_pre_ping=True,
        future=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def transactional_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        with session.begin():
            yield session
    finally:
        session.close()
