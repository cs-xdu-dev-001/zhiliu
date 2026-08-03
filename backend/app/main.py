from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.api.briefings import router as briefings_router
from app.api.items import router as items_router
from app.api.publications import router as publications_router
from app.api.runs import router as runs_router
from app.api.hermes_integration import router as hermes_integration_router
from app.api.subscriptions import router as subscriptions_router
from app.db import SessionLocal
from app.core.config import get_settings
from app.core.config import Settings
from app.mcp_server.server import SessionFactory, build_mcp_asgi
from app.seed import seed_database
from app.services.scheduler import start_scheduler, stop_scheduler


def create_app(
    *,
    start_background_scheduler: bool | None = None,
    settings: Settings | None = None,
    mcp_session_factory: SessionFactory = SessionLocal,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    should_start_scheduler = (
        runtime_settings.scheduler_enabled
        if start_background_scheduler is None
        else start_background_scheduler
    )
    mcp_server, mcp_asgi = build_mcp_asgi(
        runtime_settings.zhiliu_mcp_token,
        mcp_session_factory,
        public_base_url=runtime_settings.public_base_url,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        with SessionLocal() as db:
            seed_database(
                db,
                demo_mode=runtime_settings.demo_mode,
            )
        async with mcp_server.session_manager.run():
            if should_start_scheduler:
                start_scheduler()
            yield
            if should_start_scheduler:
                stop_scheduler()

    application = FastAPI(title="知流", version="0.1.0", lifespan=lifespan)
    application.include_router(subscriptions_router)
    application.include_router(items_router)
    application.include_router(briefings_router)
    application.include_router(publications_router)
    application.include_router(runs_router)
    application.include_router(hermes_integration_router)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "zhiliu"}

    application.mount("/api", mcp_asgi)

    return application


app = create_app()
