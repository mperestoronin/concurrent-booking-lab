class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


def booked():
    return DomainError(409, "RESOURCE_ALREADY_BOOKED", "Ресурс уже забронирован")


def invalid_hold():
    return DomainError(409, "HOLD_EXPIRED_OR_INVALID", "Удержание истекло или не принадлежит клиенту")
