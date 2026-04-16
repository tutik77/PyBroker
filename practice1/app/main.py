from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from app.bootstrap import Container, build_container
from app.exceptions import DomainError
from app.schemas import (
    NewProductInput,
    OrderItemInput,
    PlaceOrderInput,
    UpdateEmailInput,
)

logger = logging.getLogger(__name__)


def scenario_add_products(container: Container, tag: str) -> list[int]:
    logger.info("scenario 3: adding products atomically")
    specs = [
        NewProductInput(product_name=f"Mechanical Keyboard [{tag}]", price=Decimal("129.99")),
        NewProductInput(product_name=f"Wireless Mouse [{tag}]", price=Decimal("49.50")),
        NewProductInput(product_name=f"USB-C Hub [{tag}]", price=Decimal("25.00")),
    ]
    product_ids: list[int] = []
    for spec in specs:
        try:
            product = container.products.add_product(spec)
            logger.info(
                "  added #%s %s @ %s",
                product.product_id,
                product.product_name,
                product.price,
            )
            product_ids.append(product.product_id)
        except DomainError as exc:
            logger.warning("  skipped %s: %s", spec.product_name, exc)
    return product_ids


def scenario_place_order(container: Container, customer_id: int, product_ids: list[int]) -> int:
    logger.info("scenario 1: placing order")
    payload = PlaceOrderInput(
        customer_id=customer_id,
        items=[
            OrderItemInput(product_id=product_ids[0], quantity=1),
            OrderItemInput(product_id=product_ids[1], quantity=2),
            OrderItemInput(product_id=product_ids[2], quantity=3),
        ],
    )
    order = container.orders.place_order(payload)
    logger.info(
        "  order #%s placed for customer %s, total=%s, items=%d",
        order.order_id,
        order.customer_id,
        order.total_amount,
        len(order.items),
    )
    return order.order_id


def scenario_update_email(container: Container, customer_id: int, new_email: str) -> None:
    logger.info("scenario 2: updating customer email")
    updated = container.customers.update_email(
        UpdateEmailInput(customer_id=customer_id, new_email=new_email)
    )
    logger.info("  customer #%s email -> %s", updated.customer_id, updated.email)


def create_demo_customer(container: Container, tag: str) -> int:
    customer = container.customers.create(
        first_name="Alice",
        last_name="Walker",
        email=f"alice+{tag}@example.com",
    )
    logger.info("created demo customer #%s <%s>", customer.customer_id, customer.email)
    return customer.customer_id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    container = build_container()
    tag = uuid.uuid4().hex[:8]

    customer_id = create_demo_customer(container, tag)
    product_ids = scenario_add_products(container, tag)
    scenario_place_order(container, customer_id, product_ids)
    scenario_update_email(container, customer_id, f"alice+{tag}-updated@example.com")

    logger.info("done")


if __name__ == "__main__":
    main()
