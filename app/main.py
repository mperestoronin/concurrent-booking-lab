import logging
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from starlette.exceptions import HTTPException

from app.config import Settings
from app.errors import DomainError
from app.models import (
    BookingRequest, BookingResponse, ErrorResponse, HoldRequest, HoldResponse, ResourceResponse,
)
from app.repository import Repository
from app.service import BookingService

logger = logging.getLogger(__name__)


def error_response(status, code, message, headers=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}},
                        headers=headers)


def create_app(settings=None, hooks=None):
    settings = settings or Settings.from_env()
    repository = Repository(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True,
                           socket_connect_timeout=3, socket_timeout=3)
    service = BookingService(repository, redis, settings, hooks)

    @asynccontextmanager
    async def lifespan(application):
        try:
            repository.migrate()
            redis.ping()
            yield
        finally:
            redis.close()

    application = FastAPI(
        title="Учебный сервис бронирования", version="0.1.0", lifespan=lifespan,
        responses={
            404: {"model": ErrorResponse, "description": "Ресурс, бронь или путь не найдены"},
            405: {"model": ErrorResponse, "description": "Метод недоступен"},
            422: {"model": ErrorResponse, "description": "Ошибка полей, JSON или UUID"},
            500: {"model": ErrorResponse, "description": "Неожиданная ошибка реализации"},
            503: {"model": ErrorResponse, "description": "Хранилище недоступно"},
        },
    )
    conflict = {409: {"model": ErrorResponse, "description": "Конфликт брони или удержания"}}
    application.state.service = service

    @application.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(422, "VALIDATION_ERROR", "Проверьте поля запроса и формат UUID")

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, code, "Путь или метод запроса недоступен",
                              headers=exc.headers)

    @application.exception_handler(RedisConnectionError)
    @application.exception_handler(RedisTimeoutError)
    @application.exception_handler(psycopg.OperationalError)
    async def dependency_error(request, exc):
        logger.exception("Хранилище недоступно")
        return error_response(503, "DEPENDENCY_UNAVAILABLE", "Хранилище временно недоступно")

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        logger.exception("Необработанная ошибка приложения")
        return error_response(500, "INTERNAL_ERROR", "Внутренняя ошибка сервиса")

    @application.get("/health")
    def health():
        with repository.connect() as conn:
            conn.execute("SELECT 1")
        redis.ping()
        return {"status": "ok", "postgres": "ok", "redis": "ok"}

    @application.get("/resources", response_model=list[ResourceResponse])
    def resources():
        return repository.list_resources()

    @application.post("/holds", status_code=201, response_model=HoldResponse, responses=conflict)
    def hold(body: HoldRequest):
        return service.create_hold(body)

    @application.post("/bookings", status_code=201, response_model=BookingResponse, responses=conflict)
    def booking(body: BookingRequest):
        return service.confirm(body)

    @application.get("/bookings/{booking_id}", response_model=BookingResponse)
    def get_booking(booking_id: UUID):
        result = repository.get_booking(booking_id)
        if result is None:
            raise DomainError(404, "BOOKING_NOT_FOUND", "Бронь не найдена")
        return result

    @application.delete("/holds", status_code=204, responses={
        **conflict, 501: {"model": ErrorResponse, "description": "Заготовка дополнения A"},
    })
    def release(body: BookingRequest):
        service.release(body)
        return Response(status_code=204)

    return application


app = create_app()
