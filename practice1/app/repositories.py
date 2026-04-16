from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Order, Product


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_update(self, customer_id: int) -> Customer | None:
        stmt = (
            select(Customer)
            .where(Customer.customer_id == customer_id)
            .with_for_update()
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def email_exists(self, email: str, *, exclude_customer_id: int | None = None) -> bool:
        stmt = select(Customer.customer_id).where(Customer.email == email)
        if exclude_customer_id is not None:
            stmt = stmt.where(Customer.customer_id != exclude_customer_id)
        return self._session.execute(stmt).first() is not None

    def add(self, customer: Customer) -> Customer:
        self._session.add(customer)
        self._session.flush()
        return customer


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_many_locked(self, product_ids: list[int]) -> dict[int, Product]:
        if not product_ids:
            return {}
        stmt = (
            select(Product)
            .where(Product.product_id.in_(product_ids))
            .with_for_update()
        )
        rows = self._session.execute(stmt).scalars().all()
        return {p.product_id: p for p in rows}

    def name_exists(self, product_name: str) -> bool:
        stmt = select(Product.product_id).where(Product.product_name == product_name)
        return self._session.execute(stmt).first() is not None

    def add(self, product: Product) -> Product:
        self._session.add(product)
        self._session.flush()
        return product


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, order: Order) -> Order:
        self._session.add(order)
        self._session.flush()
        return order
