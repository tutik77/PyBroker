class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class CustomerNotFoundError(NotFoundError):
    pass


class ProductNotFoundError(NotFoundError):
    pass


class DuplicateEmailError(DomainError):
    pass


class DuplicateProductError(DomainError):
    pass


class EmptyOrderError(DomainError):
    pass


class InvalidQuantityError(DomainError):
    pass
