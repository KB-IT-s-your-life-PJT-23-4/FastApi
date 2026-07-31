from fastapi import FastAPI

from app.api.exception_handlers import (
    register_exception_handlers
)
from app.api.v1.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        debug = settings.debug,
        version="1.0.0"
    )

    application.include_router(
        api_router,
        prefix="/api/v1"
    )

    register_exception_handlers(application)

    return application

app = create_app()