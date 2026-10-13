import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.logging import get_logger, bind_contextvars, clear_contextvars

logger = get_logger("app.access")

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every incoming HTTP request has a correlation ID for tracing.
    Extracts X-Correlation-ID or X-Request-ID from headers, or generates a new UUID.
    Binds the correlation ID to structlog contextvars, logs request duration/metrics,
    and attaches correlation ID headers to the response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        clear_contextvars()
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else None

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.info(
                "HTTP request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
            )

            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "HTTP request error",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                client_ip=client_ip,
                error=str(exc),
                exc_info=True,
            )
            raise
        finally:
            clear_contextvars()
