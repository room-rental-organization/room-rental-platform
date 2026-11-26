import logging
from time import perf_counter
from app.core.query_metrics import QueryCount, request_queries

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import get_db


logger = logging.getLogger(__name__)


app = FastAPI(title="Room Rental Platform API")
cors_allowed_origins = [
    origin.strip()
    for origin in get_settings().cors_allowed_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router)


@app.middleware('http')
async def log_request_queries(request: Request, call_next):
    counts = QueryCount()
    token = request_queries.set(counts)
    started = perf_counter()
    try:
        response = await call_next(request)
        route = request.scope.get('route')
        logger.info('api_performance route=%s method=%s status=%d selects=%d statements=%d duration_ms=%.1f',
                    getattr(route, 'path', 'unmatched'), request.method, response.status_code,
                    counts.selects, counts.statements, (perf_counter() - started) * 1000)
        return response
    finally:
        request_queries.reset(token)


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors)},
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database")
def database_health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable.",
        ) from exc

    return {"status": "ok", "database": "ok"}
