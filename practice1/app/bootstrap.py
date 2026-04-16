from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory
from app.models import Base
from app.services import CustomerService, OrderService, ProductService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    session_factory: sessionmaker[Session]
    orders: OrderService
    customers: CustomerService
    products: ProductService


def wait_for_database(
    session_factory: sessionmaker[Session],
    *,
    attempts: int = 30,
    delay_seconds: float = 1.0,
) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.info("database not ready, retry %s/%s", attempt, attempts)
            time.sleep(delay_seconds)


def build_container(*, create_schema: bool = True) -> Container:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    wait_for_database(session_factory)

    if create_schema:
        Base.metadata.create_all(engine)

    return Container(
        settings=settings,
        session_factory=session_factory,
        orders=OrderService(session_factory),
        customers=CustomerService(session_factory),
        products=ProductService(session_factory),
    )
