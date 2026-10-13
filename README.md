# Bulk Certificate Generator API

An asynchronous, robust backend API designed to handle bulk generation of personalized PDF certificates.

## Overview
This API allows clients to submit large batches of recipients. It processes the certificate generation (via ReportLab) in the background so the client isn't blocked. It handles partial failures gracefully—one invalid recipient will not prevent the rest of the batch from succeeding.

## Tech Stack
- **Framework:** FastAPI
- **Storage Abstraction:** LocalStorageBackend & S3StorageBackend (AWS S3 & MinIO via `boto3`)
- **Task Queue & Broker:** Celery + Redis
- **Structured Logging & Tracing:** `structlog` (JSON format) with contextvars correlation IDs (`X-Correlation-ID`)
- **Health Checks & Probes:** Active Readiness & Liveness endpoint at `/healthz` (Database & Storage verification)
- **Authentication:** API Key via Security Headers (`X-API-Key`)
- **Rate Limiting:** SlowAPI (Token bucket / IP-based limiting)
- **Database:** SQLite (Default, SQLAlchemy ORM used for easy PostgreSQL migration)
- **Migrations:** Alembic
- **PDF Generation:** ReportLab
- **Validation:** Pydantic
- **Testing:** Pytest

## Setup & Running Locally

1. **Clone and Setup Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Environment Setup:**
   Copy the example environment file:
   ```bash
   cp .env.example .env  # On Windows CMD: copy .env.example .env
   ```
   Configure your security, broker, and storage credentials:
   - `API_KEY`: Secret API key for authentication (default: `dev-secret-key-12345`).
   - `API_KEY_NAME`: Header name (default: `X-API-Key`).
   - `RATE_LIMIT_JOBS`: Rate limit for job submission (default: `5/minute`).
   - `REDIS_URL`: Redis broker URL (default: `redis://localhost:6379/0`).
   - `STORAGE_TYPE`: `local` (default) or `s3`.
   - `S3_BUCKET_NAME`: Target S3 / MinIO bucket name (default: `certificates`).
   - `S3_ENDPOINT_URL`: Custom S3 endpoint URL for MinIO (e.g. `http://minio:9000`) or leave blank for AWS.
   - `S3_ACCESS_KEY` & `S3_SECRET_KEY`: AWS or MinIO credentials.
   - `S3_REGION`: Region name (default: `us-east-1`).

4. **Run Database Migrations:**
   Apply version-controlled schema migrations:
   ```bash
   alembic upgrade head
   ```

5. **Run the Application:**
   Start the FastAPI web server:
   ```bash
   uvicorn app.main:app --reload
   ```
   In a separate terminal, start the Celery worker:
   ```bash
   celery -A app.core.celery_app.celery_app worker --loglevel=info
   ```
   The API will be available at `http://127.0.0.1:8000`. Navigating to the root URL will automatically redirect you to the interactive API documentation at `http://127.0.0.1:8000/docs`. In Swagger UI, click **Authorize** to provide your `X-API-Key`.

## Running with Docker
Run the entire stack (FastAPI app, Redis broker with AOF persistence, and Celery worker) using Docker Compose:
```bash
docker-compose up --build
```

## Running Tests
To run the automated test suite, ensure your virtual environment is activated and run:
```bash
python -m pytest
```

## Security & Rate Limiting

- **API Key Header Authentication:** All `/api/v1/*` routes require the `X-API-Key` header with a valid key. Requests with missing or invalid keys receive `401 Unauthorized`.
- **IP-Based Rate Limiting:** `POST /api/v1/jobs/` is protected with SlowAPI to a maximum of 5 requests per minute per IP address. Exceeding this returns `429 Too Many Requests`.

## Example `curl` Requests

*(Note: Replace `{job_id}` and `{certificate_id}` with the actual UUIDs returned by the API. Use `-H "X-API-Key: dev-secret-key-12345"` for authentication).*

### 1. Submit a Job (Rate-Limited to 5 req/min per IP)
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: dev-secret-key-12345" \
     -d '{
       "course_name": "Advanced Backend Engineering",
       "issue_date": "2024-10-07",
       "recipients": [
         {"name": "Alice Smith", "email": "alice@example.com"},
         {"name": "Bob Jones", "email": "bob@example.com"}
       ]
     }'
```

### 2. Check Job Status & Progress
```bash
curl "http://127.0.0.1:8000/api/v1/jobs/{job_id}" \
     -H "X-API-Key: dev-secret-key-12345"
```

### 3. Retrieve Paginated Certificates
```bash
curl "http://127.0.0.1:8000/api/v1/jobs/{job_id}/certificates?page=1&page_size=50" \
     -H "X-API-Key: dev-secret-key-12345"
```

### 4. Download a Single Certificate PDF
```bash
curl -O -J "http://127.0.0.1:8000/api/v1/certificates/{certificate_id}/download" \
     -H "X-API-Key: dev-secret-key-12345"
```

### 5. Download ZIP of All Successful Certificates
```bash
curl -O -J "http://127.0.0.1:8000/api/v1/jobs/{job_id}/download" \
     -H "X-API-Key: dev-secret-key-12345"
```

### 6. Active Health Check Probe (`/healthz`)
No API key required (public for container orchestrators, Kubernetes, or load balancers):
```bash
curl "http://127.0.0.1:8000/healthz"
```
Response (`200 OK` when healthy, `503 Service Unavailable` when degraded):
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "up"
    },
    "storage": {
      "status": "up",
      "backend": "local"
    }
  }
}
```

## Structured Logging & Request Tracing

- **JSON Log Formatting:** Configured via `structlog` across all FastAPI HTTP routes and Celery background workers. Each log line is rendered as structured JSON containing timestamp, log level, event, logger name, and contextual attributes.
- **Correlation IDs (`X-Correlation-ID` & `X-Request-ID`):**
  - Incoming requests are inspected for `X-Correlation-ID` or `X-Request-ID`. If neither is provided, a UUIDv4 correlation ID is automatically generated.
  - The correlation ID is bound to Python `contextvars` via `structlog.contextvars.bind_contextvars(correlation_id=...)`, automatically enriching all log entries emitted during request handling.
  - Responses mirror the correlation ID in both `X-Correlation-ID` and `X-Request-ID` headers.
  - When submitting a job, the correlation ID is propagated directly into the Celery worker task (`process_job.delay(..., correlation_id=...)`), ensuring end-to-end tracing across HTTP lifecycles and background worker processes.


## Project Structure
```text
bulk_certificate_generator/
├── app/
│   ├── api/             # API routing (jobs, certificates)
│   ├── core/            # Config, exceptions, utils, database setup
│   ├── models/          # SQLAlchemy Database Models
│   ├── schemas/         # Pydantic schemas (Request/Response validation)
│   ├── services/        # Business logic & PDF generation orchestrator
│   ├── workers/         # Background processing logic
│   └── main.py          # Application entry point
├── storage/             # Locally generated PDFs and ZIPs
├── tests/               # Pytest suite
├── .github/             # CI/CD workflows
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Design Decisions

- **Why FastAPI?** FastAPI provides native async support, automated OpenAPI documentation, and incredibly fast request parsing/validation via Pydantic.
- **Storage Abstraction Layer (Factory Pattern):** Implemented an extensible storage abstraction (`BaseStorageBackend`) supporting both `LocalStorageBackend` (for local development/testing) and `S3StorageBackend` (via `boto3` for AWS S3 and MinIO). Components interact only with the interface, allowing storage backends to be toggled via environment variables without code modifications.
- **Direct Cloud Object Streaming:** Certificates and ZIP archives stored in S3/MinIO are streamed directly to clients via `StreamingResponse` using chunked byte iterators (`s3_obj['Body'].iter_chunks()`), preventing Out-Of-Memory (OOM) bottlenecks and avoiding buffering large files on disk or in API process memory.
- **Distributed Task Queue with Celery & Redis:** Replaced in-memory background tasks with Celery and Redis. Submitting a job enqueues a persistent task in Redis and returns `202 Accepted` immediately, offloading heavy CPU/PDF rendering to background workers.
- **Task Persistence Across Restarts:** Tasks are protected against worker crashes or restarts using Celery's `task_acks_late=True` and `task_reject_on_worker_lost=True`. Redis runs with Append-Only File (`appendonly yes`) persistence and a dedicated volume mount, ensuring no jobs are lost during container or system reboots.
- **Exponential Backoff Retries for Transient Errors:** Background certificate generation automatically retries transient PDF generation and storage I/O errors (`CertificateGenerationError`, `OSError`, `IOError`) using exponential backoff (`delay = base_delay * 2^attempt`) before flagging any certificate as permanently failed. The Celery task itself is configured with `autoretry_for` and `retry_backoff=True` for resilient database reconnects.
- **Per-Certificate Failure Isolation:** If 999 recipients are valid but 1 has a malformed email, the system isolates validation/generation failures on a per-certificate basis, ensuring the rest of the batch succeeds.
- **Atomic Job Claims & Counters:** The background worker uses a database `UPDATE ... WHERE status IN ('PENDING', 'PROCESSING')` claim system to prevent race conditions and allow graceful resumption after restarts. Atomic SQL expressions safely update job progress.
- **Temp-File ZIP Streaming:** To prevent Out-Of-Memory (OOM) errors on large jobs, the ZIP download endpoint builds the archive from storage objects and uploads/streams it directly via the active storage backend.

## Future Scope

1. **Idempotency Keys:** Implement idempotency keys for the POST endpoint to prevent duplicate submissions from clients experiencing network retries.
2. **Monitoring & Metrics:** Add Prometheus and Flower metrics to monitor Celery queues, task latency, and worker health.


