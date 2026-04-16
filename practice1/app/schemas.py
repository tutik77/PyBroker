from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PositiveInt


class OrderItemInput(BaseModel):
    product_id: PositiveInt
    quantity: PositiveInt


class PlaceOrderInput(BaseModel):
    customer_id: PositiveInt
    items: list[OrderItemInput] = Field(min_length=1)


class NewProductInput(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0, decimal_places=2)


class UpdateEmailInput(BaseModel):
    customer_id: PositiveInt
    new_email: EmailStr


class OrderItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_item_id: int
    product_id: int
    quantity: int
    subtotal: Decimal


class OrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    customer_id: int
    order_date: datetime
    total_amount: Decimal
    items: list[OrderItemView]


class CustomerView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    first_name: str
    last_name: str
    email: str


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    price: Decimal
