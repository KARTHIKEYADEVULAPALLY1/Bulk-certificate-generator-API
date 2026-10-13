import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Security
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text, update
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import app.models  # Ensures models are registered
from app.api.v1.certificates import router as certificates_router
from app.api.v1.jobs import router as jobs_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import get_logger, setup_logging
from app.core.middleware import CorrelationIdMiddleware
from app.core.rate_limit import limiter
from app.core.security import verify_api_key
from app.models.enums import JobStatus
from app.models.job import Job
from app.services.storage import get_storage_backend

setup_logging(log_level=settings.log_level)
logger = get_logger("app.main")

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.storage_dir, exist_ok=True)
    logger.info("Application starting up", storage_dir=settings.storage_dir)
    
    # Startup recovery: mark stuck PROCESSING jobs as FAILED.
    # I chose to mark them as FAILED rather than re-queueing them because without strong idempotency 
    # guarantees on the PDF generation (or partial file cleanup checks), automatically retrying could 
    # result in corrupted state, duplicate partial files, or infinite crash loops.
    with SessionLocal() as db:
        timeout = datetime.utcnow() - timedelta(minutes=60)
        stmt = (
            update(Job)
            .where(Job.status == JobStatus.PROCESSING, Job.updated_at < timeout)
            .values(status=JobStatus.FAILED)
        )
        db.execute(stmt)
        db.commit()
    yield
    logger.info("Application shutting down")

app = FastAPI(title="Bulk Certificate Generator API", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(
    jobs_router,
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Security(verify_api_key)],
)
app.include_router(
    certificates_router,
    prefix="/api/v1/certificates",
    tags=["certificates"],
    dependencies=[Security(verify_api_key)],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/healthz")
def healthz_check(type: str | None = None):
    db_status = "up"
    db_error = None
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1")).scalar()
    except Exception as exc:
        db_status = "down"
        db_error = str(exc)

    storage_status = "up"
    storage_error = None
    storage_backend_name = settings.storage_type
    try:
        storage = get_storage_backend()
        healthy, err = storage.check_health()
        if not healthy:
            storage_status = "down"
            storage_error = err
    except Exception as exc:
        storage_status = "down"
        storage_error = str(exc)

    is_healthy = (db_status == "up") and (storage_status == "up")
    payload = {
        "status": "healthy" if is_healthy else "unhealthy",
        "checks": {
            "database": {
                "status": db_status,
                **({"error": db_error} if db_error else {}),
            },
            "storage": {
                "status": storage_status,
                "backend": storage_backend_name,
                **({"error": storage_error} if storage_error else {}),
            },
        },
    }

    if not is_healthy:
        logger.warning(
            "Health check degraded",
            health_status=payload["status"],
            checks=payload["checks"],
        )
        return JSONResponse(status_code=503, content=payload)

    return JSONResponse(status_code=200, content=payload)

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")

# Static files and Web Dashboard
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/dashboard", include_in_schema=False)
    def serve_dashboard():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return RedirectResponse(url="/docs")

