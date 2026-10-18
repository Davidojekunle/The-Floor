from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.openapi import GLOBAL_RESPONSES, operation_id


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Every error uses the shape `{ \"error\": { \"code\", \"message\", \"fields\"? } }`. "
            "Send `Authorization: Bearer <access_token>` on all routes except register and login."
        ),
        generate_unique_id_function=operation_id,
        responses=GLOBAL_RESPONSES,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
