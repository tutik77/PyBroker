from __future__ import annotations

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.exceptions import (
    CustomerNotFoundError,
    DuplicateEmailError,
    DuplicateProductError,
    ProductNotFoundError,
)
from app.models import Customer, Order, OrderItem, Product
from app.schemas import (
    CustomerView,
    NewProductInput,
    OrderView,
    PlaceOrderInput,
    ProductView,
    UpdateEmailInput,
)
from app.unit_of_work import UnitOfWork


class OrderService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def place_order(self, payload: PlaceOrderInput) -> OrderView:
        with UnitOfWork(self._session_factory) as uow:
            customer = uow.customers.get_for_update(payload.customer_id)
            if customer is None:
                raise CustomerNotFoundError(f"customer {payload.customer_id} not found")

            product_ids = [item.product_id for item in payload.items]
            products = uow.products.get_many_locked(product_ids)

            missing = set(product_ids) - products.keys()
            if missing:
                raise ProductNotFoundError(f"products not found: {sorted(missing)}")

            order = Order(customer_id=customer.customer_id, total_amount=Decimal("0"))
            for line in payload.items:
                product = products[line.product_id]
                subtotal = (product.price * line.quantity).quantize(Decimal("0.01"))
                order.items.append(
                    OrderItem(
                        product_id=product.product_id,
                        quantity=line.quantity,
                        subtotal=subtotal,
                    )
                )
            order.total_amount = sum((item.subtotal for item in order.items), Decimal("0"))

            uow.orders.add(order)
            return OrderView.model_validate(order)


class CustomerService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def update_email(self, payload: UpdateEmailInput) -> CustomerView:
        with UnitOfWork(self._session_factory) as uow:
            customer = uow.customers.get_for_update(payload.customer_id)
            if customer is None:
                raise CustomerNotFoundError(f"customer {payload.customer_id} not found")

            if customer.email == payload.new_email:
                return CustomerView.model_validate(customer)

            if uow.customers.email_exists(
                payload.new_email, exclude_customer_id=customer.customer_id
            ):
                raise DuplicateEmailError(f"email {payload.new_email} already in use")

            customer.email = payload.new_email
            try:
                uow.session.flush()
            except IntegrityError as exc:
                raise DuplicateEmailError(f"email {payload.new_email} already in use") from exc

            return CustomerView.model_validate(customer)

    def create(self, first_name: str, last_name: str, email: str) -> CustomerView:
        with UnitOfWork(self._session_factory) as uow:
            if uow.customers.email_exists(email):
                raise DuplicateEmailError(f"email {email} already in use")
            customer = Customer(first_name=first_name, last_name=last_name, email=email)
            uow.customers.add(customer)
            return CustomerView.model_validate(customer)


class ProductService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add_product(self, payload: NewProductInput) -> ProductView:
        with UnitOfWork(self._session_factory) as uow:
            if uow.products.name_exists(payload.product_name):
                raise DuplicateProductError(
                    f"product '{payload.product_name}' already exists"
                )

            product = Product(product_name=payload.product_name, price=payload.price)
            try:
                uow.products.add(product)
            except IntegrityError as exc:
                raise DuplicateProductError(
                    f"product '{payload.product_name}' already exists"
                ) from exc

            return ProductView.model_validate(product)
