from dataclasses import dataclass
from typing import Callable


def noop():
    pass


@dataclass
class Hooks:
    """Контрольные точки для тестов. По HTTP их включить нельзя."""

    after_hold_read: Callable[[], None] = noop
    before_booking_insert: Callable[[], None] = noop
    after_authorization: Callable[[], None] = noop
    before_release_delete: Callable[[], None] = noop
