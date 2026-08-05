from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.routes import router
from app.api.celebrate import router as celebrate_router
from app.api.integrations import router as integrations_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.db.seed import register_handlers, seed_database
from app.db.session import Base, SessionLocal, engine
from app.schemas import HealthOut

setup_logging("DEBUG" if settings.debug else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    register_handlers()
    if settings.seed_on_startup and settings.environment != "test":
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(router, prefix="/api")
app.include_router(celebrate_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "request_id": request.headers.get("X-Request-ID"),
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    logger.warning("Integrity error: %s", exc)
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflict with existing data", "request_id": request.headers.get("X-Request-ID")},
    )


@app.get("/")
def root():
    """Railway / browsers hit `/`; API lives under `/api`."""
    return {
        "service": settings.app_name,
        "product": "Revisit",
        "platform": settings.argus_product_line,
        "version": settings.app_version,
        "status": "ok",
        "app": settings.frontend_base_url,
        "health": "/health",
        "ready": "/ready",
        "api": "/api",
    }


@app.get("/health", response_model=HealthOut)
def health():
    return HealthOut(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        database="unchecked",
        environment=settings.environment,
    )


@app.get("/ready", response_model=HealthOut)
def ready():
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness DB check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": settings.app_name,
                "version": settings.app_version,
                "database": "error",
                "environment": settings.environment,
            },
        )
    return HealthOut(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        database=db_status,
        environment=settings.environment,
    )
