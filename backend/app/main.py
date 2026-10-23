import asyncio
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.openapi import GLOBAL_RESPONSES, operation_id
from app.core.security_headers import SecurityHeaders
import app.realtime.events  # noqa: F401  (registers the commit hooks that send live events)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the email sender in this process (same one-worker rule as live updates)."""
    from app.db.session import get_db
    from app.services.email_service import run_sender

    settings = get_settings()
    task = None
    if settings.email_sender_enabled:
        factory = app.dependency_overrides.get(get_db, get_db)
        task = asyncio.create_task(run_sender(factory, settings.email_send_interval_seconds))
    yield
    if task is not None:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Every error uses the shape `{ \"error\": { \"code\", \"message\", \"fields\"? } }`. "
            "Send `Authorization: Bearer <access_token>` on all routes except register and login."
        ),
        generate_unique_id_function=operation_id,
        responses=GLOBAL_RESPONSES,
        # in production (the built site is served) the interactive API docs are off; locally they stay on
        **({"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.frontend_dist else {}),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # the app's JS shrinks from ~530 KB to ~160 KB
    app.add_middleware(SecurityHeaders)

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    if settings.frontend_dist:
        mount_frontend(app, Path(settings.frontend_dist), settings.api_v1_prefix)
    return app


class ImmutableFiles(StaticFiles):
    """Vite puts a content hash in every asset name, so browsers can keep them for a year."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_frontend(app: FastAPI, dist: Path, api_prefix: str) -> None:
    """Serve the built single-page app: hashed assets cached forever, every other path gets index.html."""
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    dist = dist.resolve()
    index = dist / "index.html"
    app.mount("/assets", ImmutableFiles(directory=dist / "assets"), name="assets")
    api_root = api_prefix.strip("/").split("/")[0]  # "api"

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str, request: Request):
        if path == api_root or path.startswith(api_root + "/"):
            raise StarletteHTTPException(status_code=404)  # unknown API route: JSON 404, never the page
        home = urlsplit(get_settings().frontend_url)
        host = request.url.hostname or ""
        if host.endswith(".onrender.com") and home.hostname and home.hostname != host:
            # pages on the old address move to the real domain, so search engines index one site.
            # Only pages: the API and the live socket keep working there for tabs that are already open.
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"{home.scheme}://{home.netloc}/{path}{query}", status_code=301)
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            # the service worker must be re-checked on every visit, or an old one lingers for a day
            return FileResponse(file, headers={"Cache-Control": "no-cache"} if path == "sw.js" else None)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
