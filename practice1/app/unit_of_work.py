from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.repositories import CustomerRepository, OrderRepository, ProductRepository


class UnitOfWork:
    customers: CustomerRepository
    products: ProductRepository
    orders: OrderRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self._session.begin()
        self.customers = CustomerRepository(self._session)
        self.products = ProductRepository(self._session)
        self.orders = OrderRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    @property
    def session(self) -> Session:
        assert self._session is not None, "UnitOfWork is not active"
        return self._session
