import json
from uuid import uuid4

from app.errors import DomainError, booked, invalid_hold
from app.hooks import Hooks


class BookingService:
    def __init__(self, repository, redis, settings, hooks=None):
        self.repository = repository
        self.redis = redis
        self.settings = settings
        self.hooks = hooks or Hooks()

    def key(self, resource_id):
        return f"{self.settings.key_prefix}hold:{resource_id}"

    def require_resource(self, resource_id):
        if not self.repository.resource_exists(resource_id):
            raise DomainError(404, "RESOURCE_NOT_FOUND", "Ресурс не найден")

    def create_hold(self, request):
        self.require_resource(request.resourceId)
        if self.repository.has_booking(request.resourceId):
            raise booked()
        key = self.key(request.resourceId)
        # TODO A: два клиента могут прочитать отсутствие одного и того же ключа.
        if self.redis.get(key) is not None:
            raise DomainError(409, "RESOURCE_HELD", "Ресурс уже удерживается")
        self.hooks.after_hold_read()
        hold_id = uuid4()
        value = json.dumps({"holdId": str(hold_id), "clientId": request.clientId}, sort_keys=True)
        self.redis.set(key, value, px=request.ttlSeconds * 1000)
        return {"resourceId": request.resourceId, "holdId": hold_id,
                "expiresInSeconds": request.ttlSeconds}

    def confirm(self, request):
        self.require_resource(request.resourceId)
        if self.repository.has_booking(request.resourceId):
            raise booked()
        raw = self.redis.get(self.key(request.resourceId))
        # TODO C: отсутствие ключа и неверный holdId сейчас ошибочно допускаются.
        if raw is not None and json.loads(raw)["clientId"] != request.clientId:
            raise invalid_hold()
        self.hooks.after_authorization()
        self.hooks.before_booking_insert()
        booking_id = uuid4()
        # TODO B: SELECT до INSERT не защищает от конкурентной транзакции.
        # После добавления ограничения обработайте его конфликт по контракту.
        self.repository.insert_booking(booking_id, request)
        # Ключ оставляем доживать TTL, чтобы не удалить новое удержание другого клиента.
        return {"bookingId": booking_id, "resourceId": request.resourceId, "status": "CONFIRMED"}

    def release(self, request):
        # Дополнение A: атомарно проверьте владельца и удалите только его ключ.
        raise DomainError(501, "NOT_IMPLEMENTED", "Дополнительное задание ещё не выполнено")
