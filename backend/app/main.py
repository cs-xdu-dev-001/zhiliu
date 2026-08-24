from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.api.briefings import router as briefings_router
from app.api.items import router as items_router
from app.api.publications import router as publications_router
from app.api.runs import router as runs_router
from app.api.hermes_integration import router as hermes_integration_router
from app.api.subscriptions import router as subscriptions_router
from app.api.search import router as search_router
from app.api.preferences import router as preferences_router
from app.api.quality import router as quality_router
from app.api.subscription_health import router as subscription_health_router
from app.api.saved_views import router as saved_views_router
from app.api.diagnostics import router as diagnostics_router
from app.api.daily_attention import router as daily_attention_router
from app.api.feedback import router as feedback_router
from app.db import SessionLocal, get_db
from app.api.topics import router as topics_router
from app.core.config import get_settings
from app.core.config import Settings
from app.mcp_server.server import SessionFactory, build_mcp_asgi
from app.middleware import SafeRequestLogMiddleware
from app.seed import seed_database
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.topics import reconcile_topics


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
        with mcp_session_factory() as db:
            seed_database(
                db,
                demo_mode=runtime_settings.demo_mode,
            )
            reconcile_topics(db)
        async with mcp_server.session_manager.run():
            if should_start_scheduler:
                start_scheduler()
            yield
            if should_start_scheduler:
                stop_scheduler()

    application = FastAPI(title="知流", version="0.1.0", lifespan=lifespan)
    application.add_middleware(SafeRequestLogMiddleware)
    application.dependency_overrides[get_settings] = lambda: runtime_settings
    application.include_router(subscriptions_router)
    application.include_router(items_router)
    application.include_router(briefings_router)
    application.include_router(publications_router)
    application.include_router(runs_router)
    application.include_router(hermes_integration_router)
    application.include_router(search_router)
    application.include_router(preferences_router)
    application.include_router(quality_router)
    application.include_router(subscription_health_router)
    application.include_router(saved_views_router)
    application.include_router(diagnostics_router)
    application.include_router(topics_router)
    application.include_router(daily_attention_router)
    application.include_router(feedback_router)

    @application.get("/api/health")
    def health(db: Session = Depends(get_db)) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="数据库暂时不可用",
            ) from error
        return {"status": "ok", "service": "zhiliu"}

    application.mount("/api", mcp_asgi)

    return application


app = create_app()
