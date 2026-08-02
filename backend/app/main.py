from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.api.briefings import router as briefings_router
from app.api.items import router as items_router
from app.api.runs import router as runs_router
from app.api.hermes_integration import router as hermes_integration_router
from app.api.subscriptions import router as subscriptions_router
from app.db import Base, engine
from app.db import SessionLocal
from app.core.config import get_settings
from app.seed import seed_database
from app.services.scheduler import start_scheduler, stop_scheduler


def create_app(*, start_background_scheduler: bool | None = None) -> FastAPI:
    settings = get_settings()
    should_start_scheduler = settings.scheduler_enabled if start_background_scheduler is None else start_background_scheduler

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_database(
                db,
                demo_mode=settings.demo_mode,
            )
        if should_start_scheduler:
            start_scheduler()
        yield
        if should_start_scheduler:
            stop_scheduler()

    application = FastAPI(title="知流", version="0.1.0", lifespan=lifespan)
    application.include_router(subscriptions_router)
    application.include_router(items_router)
    application.include_router(briefings_router)
    application.include_router(runs_router)
    application.include_router(hermes_integration_router)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "zhiliu"}

    return application


app = create_app()
