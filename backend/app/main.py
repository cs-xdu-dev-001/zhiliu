from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.api.auth import router as auth_router
from app.api.briefings import router as briefings_router
from app.api.items import router as items_router
from app.api.subscriptions import router as subscriptions_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="知流", version="0.1.0", lifespan=lifespan)
    application.include_router(auth_router)
    application.include_router(subscriptions_router)
    application.include_router(items_router)
    application.include_router(briefings_router)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "zhiliu"}

    return application


app = create_app()
