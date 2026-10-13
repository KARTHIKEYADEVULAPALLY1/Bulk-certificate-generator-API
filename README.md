# Bulk Certificate Generator API

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A.svg?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg)](https://www.sqlalchemy.org/)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-orange.svg)](https://alembic.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D.svg?logo=redis&logoColor=white)](https://redis.io)
[![Tests Passing](https://img.shields.io/badge/tests-70%20passed%20%7C%20100%25-brightgreen.svg?logo=pytest&logoColor=white)](tests/)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An asynchronous, fault-tolerant, and horizontally scalable backend service engineered for **bulk generation and streaming delivery of personalized PDF certificates**.

Designed to handle large enterprise batches without blocking HTTP lifecycles, this system isolates per-recipient generation failures, guarantees at-least-once background task execution, provides pluggable cloud/local storage abstractions, and offers end-to-end distributed tracing.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Key Engineering Highlights](#key-engineering-highlights)
- [Tech Stack](#tech-stack)
- [Getting Started / Quickstart](#getting-started--quickstart)
  - [Prerequisites](#prerequisites)
  - [1. Clone Repository](#1-clone-repository)
  - [2. Virtual Environment Setup](#2-virtual-environment-setup)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Environment Configuration](#4-environment-configuration)
  - [5. Run Database Migrations](#5-run-database-migrations)
  - [6. Start Services Locally](#6-start-services-locally)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Running the Test Suite](#running-the-test-suite)
- [API Reference & Workflows](#api-reference--workflows)
  - [Interactive OpenAPI Documentation](#interactive-openapi-documentation)
  - [1. Submit a Bulk Certificate Job](#1-submit-a-bulk-certificate-job)
  - [2. Poll Job Status & Progress](#2-poll-job-status--progress)
  - [3. List Generated Certificates (Paginated)](#3-list-generated-certificates-paginated)
  - [4. Download a Single Certificate](#4-download-a-single-certificate)
  - [5. Download All Certificates as ZIP Archive](#5-download-all-certificates-as-zip-archive)
  - [6. Readiness & Liveness Probes (`/healthz`)](#6-readiness--liveness-probes-healthz)
- [Configuration Reference](#configuration-reference)
- [Project Directory Layout](#project-directory-layout)
- [Production Roadmap](#production-roadmap)

---

## System Architecture

The service decouples HTTP request handling from compute-intensive PDF rendering using a **producer-consumer architecture** powered by FastAPI, Redis, and Celery workers.

```mermaid
flowchart TD
    Client(["Client / Frontend / Integration"])
    
    subgraph Edge ["Security & Ingress"]
        AuthFilter["API Key Guard<br/><code>X-API-Key</code>"]
        RateLimiter["SlowAPI Limiter<br/>Token Bucket / IP"]
        TracingMW["Correlation Middleware<br/><code>X-Correlation-ID</code>"]
    end

    subgraph API ["FastAPI Web Application"]
        Router["FastAPI Routers<br/><code>/jobs</code> & <code>/certificates</code>"]
        HealthProbe["Active Health Probe<br/><code>/healthz</code>"]
        AsyncLifespan["Lifespan Manager<br/>Orphan Job Recovery"]
    end

    subgraph Queue ["Message Broker"]
        RedisBroker[("Redis Broker & State<br/>AOF Persistence Enabled")]
    end

    subgraph Workers ["Distributed Celery Workers"]
        CeleryWorker["Celery Worker Pool<br/><code>process_job</code> task"]
        PDFEngine["ReportLab Engine<br/>Vector Typography & Layout"]
        RetryLogic["Exponential Backoff<br/>Transient I/O Retrier"]
    end

    subgraph StorageLayer ["Storage Abstraction (Factory Pattern)"]
        StorageFactory{"Storage Factory<br/><code>BaseStorageBackend</code>"}
        LocalStorage[("Local Filesystem<br/>POSIX Storage")]
        S3Storage[("Object Storage<br/>AWS S3 / MinIO via Boto3")]
    end

    subgraph Database ["Relational State Store"]
        RDBMS[("Database Engine<br/>SQLite / PostgreSQL")]
        AlembicMgr["Alembic Migrations<br/>Versioned Schema"]
    end

    Client -->|HTTP POST / GET| TracingMW
    TracingMW --> AuthFilter
    AuthFilter --> RateLimiter
    RateLimiter --> Router
    Client -.->|Health Check| HealthProbe

    Router -->|1. Create Job & Certificates (PENDING)| RDBMS
    Router -->|2. Dispatch process_job task| RedisBroker
    Router -->|3. Immediate 202 Accepted| Client

    RedisBroker -->|Acks Late Task Delivery| CeleryWorker
    CeleryWorker -->|Fetch Batch & Atomic Claim| RDBMS
    CeleryWorker -->|Render Canvas| PDFEngine
    PDFEngine --> RetryLogic
    RetryLogic -->|Save PDF| StorageFactory

    StorageFactory -.->|STORAGE_TYPE=local| LocalStorage
    StorageFactory -.->|STORAGE_TYPE=s3| S3Storage

    Router -->|Zero-Copy Stream Download| StorageFactory
    HealthProbe -->|Ping Active Connections| RDBMS
    HealthProbe -->|Verify Read/Write Access| StorageFactory
    AlembicMgr -.->|Applies Schema Upgrades| RDBMS
```

---

## Key Engineering Highlights

### 1. Asynchronous Job Ingestion (O(1) HTTP Response Time)
Heavy PDF rendering (which involves font measurement, layout mathematics, and vector drawing) is completely decoupled from the web thread pool. When batches of up to **1,000 recipients** are submitted:
- The job and recipient stubs are atomically inserted with `PENDING` status.
- A task is dispatched via Redis.
- An immediate `202 Accepted` response is returned to the client along with polling URLs.

### 2. Resilient Worker Processing & Atomic Job Claims
- **Crash Recovery & Late Acknowledgment:** Celery is configured with `task_acks_late = True` and `task_reject_on_worker_lost = True`. If a worker container abruptly crashes or runs out of memory, Redis automatically re-delivers the job to a surviving worker.
- **Atomic Concurrency Control:** Workers use atomic SQL queries (`UPDATE jobs SET status = 'PROCESSING' WHERE status IN ('PENDING', 'PROCESSING')`) to prevent duplicate worker race conditions.
- **Orphan Job Reaping:** The FastAPI lifespan manager detects jobs left in `PROCESSING` status beyond timeout thresholds across application restarts and reconciles their states safely.

### 3. Per-Certificate Fault Isolation
A single invalid recipient record (e.g., malformed email or illegal formatting) will **never fail the entire batch**. The worker isolates failures on a per-certificate level:
- Valid certificates are marked `SUCCESS` and persisted.
- Invalid certificates are logged with detailed error traces and marked `FAILED`.
- The aggregate job status reflects partial completions accurately (`SUCCESS` vs `PARTIALLY_FAILED` vs `FAILED`).

### 4. Storage Abstraction Layer (Factory Pattern)
The service provides a unified interface (`BaseStorageBackend`) implemented by:
- **`LocalStorageBackend`**: Sandboxed local disk storage with strict directory traversal prevention (`os.path.abspath` safety assertions).
- **`S3StorageBackend`**: Cloud storage supporting **AWS S3** and **MinIO** via `boto3`.
- **Zero-Memory Cloud Streaming:** PDF downloads and bulk ZIP downloads are streamed directly using `StreamingResponse` and byte chunk iterators (`s3_obj['Body'].iter_chunks()`), bypassing intermediate disk caching and preventing Out-Of-Memory (OOM) crashes under heavy load.

### 5. Distributed Tracing & Structured JSON Logging
Configured with `structlog` and Python `contextvars`:
- Incoming requests extract or generate a unique `X-Correlation-ID` / `X-Request-ID`.
- The correlation ID is bound to the async execution context, automatically tagging all downstream logs.
- The correlation ID is forwarded directly into Celery worker tasks (`process_job.delay(..., correlation_id=...)`), creating a single observable trace across the API and worker processes.

### 6. Defense-in-Depth Security & Rate Limiting
- **API Key Guard:** Enforced on all private endpoints via `Security(verify_api_key)` with automatic `401 Unauthorized` rejection.
- **IP-Based Rate Limiting:** Enforced via `SlowAPI` on compute-heavy submission routes (`POST /api/v1/jobs/` default: 5 requests/minute per client IP), gracefully responding with `429 Too Many Requests`.

---

## Tech Stack

| Domain | Technology | Purpose & Architectural Rationale |
| :--- | :--- | :--- |
| **Framework** | **FastAPI** | High-performance ASGI framework; native async support, OpenAPI spec generation, and strict dependency injection. |
| **Data Validation** | **Pydantic v2** | Ultra-fast data serialization, input sanitization, and runtime schema enforcement. |
| **ORM & Database** | **SQLAlchemy 2.0** | Robust relational mapping, connection pooling, and atomic SQL transactions. Compatible with SQLite and PostgreSQL. |
| **Migrations** | **Alembic** | Automated, version-controlled database schema migrations. |
| **Task Queue** | **Celery 5.4+** | Production-ready distributed task queue supporting late task acks, worker concurrency, and exponential retries. |
| **Message Broker** | **Redis 7.0+** | Low-latency in-memory broker configured with Append-Only File (`AOF`) persistence for durable task dispatch. |
| **Cloud Storage** | **Boto3 (AWS S3 / MinIO)** | Unified object storage adapter with chunked streaming and presigned URL support. |
| **PDF Engine** | **ReportLab** | High-fidelity canvas rendering for custom certificate geometry, vector art, and typography. |
| **Rate Limiting** | **SlowAPI** | In-memory / Redis token-bucket rate limiter for protecting endpoints against denial-of-service abuse. |
| **Structured Logging** | **Structlog** | Standardized JSON log outputs enriched with timestamps, log levels, contextual metadata, and correlation IDs. |
| **Testing** | **Pytest & HTTPX** | Automated test suite covering unit, integration, authentication, rate limiting, and failure modes. |
| **Containers** | **Docker & Compose** | Containerized multi-service deployment orchestrating API, Worker, and Redis instances. |

---

## Getting Started / Quickstart

### Prerequisites
- **Python:** 3.11 or higher
- **Redis Server:** Running locally (`redis://localhost:6379/0`) or via Docker
- **Git**

---

### 1. Clone Repository

```bash
git clone https://github.com/KARTHIKEYADEVULAPALLY1/Bulk-certificate-generator-API.git
cd Bulk-certificate-generator-API
```

---

### 2. Virtual Environment Setup

#### On Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

#### On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

---

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 4. Environment Configuration

Copy the example environment template into your local `.env`:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows:
copy .env.example .env
```

Review or modify your `.env` configuration:
```env
DATABASE_URL=sqlite:///./certificates.sqlite
STORAGE_DIR=./storage
MAX_BATCH_SIZE=1000
API_KEY=dev-secret-key-12345
API_KEY_NAME=X-API-Key
RATE_LIMIT_JOBS=5/minute
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CERT_MAX_RETRIES=3
CERT_RETRY_BACKOFF_BASE=0.5
STORAGE_TYPE=local
S3_BUCKET_NAME=certificates
S3_ENDPOINT_URL=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=us-east-1
```

---

### 5. Run Database Migrations

Apply the version-controlled Alembic migrations to set up or update your database schema:

```bash
python -m alembic upgrade head
```

> [!NOTE]
> Alembic creates and synchronizes all relational tables (`jobs`, `certificates`) and indexes. When running tests or new environments, always execute `python -m alembic upgrade head`.

---

### 6. Start Services Locally

You will need two terminal sessions running concurrently:

#### Terminal 1: FastAPI Web Server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API Server: `http://127.0.0.1:8000`
- Interactive Swagger UI: `http://127.0.0.1:8000/docs`
- **Studio Web Dashboard:** `http://127.0.0.1:8000/dashboard`

#### Terminal 2: Celery Background Worker
```bash
# On Linux / macOS:
celery -A app.core.celery_app.celery_app worker --loglevel=info

# On Windows (use solo pool to prevent OS-level fork limitations):
celery -A app.core.celery_app.celery_app worker --loglevel=info --pool=solo
```

#### Terminal 3 (Optional): Streamlit Interactive UI
```bash
streamlit run streamlit_app.py
```
- Streamlit Web App: `http://localhost:8501`

---

## Interactive Frontend Interfaces

The project provides two visual frontend experiences to submit jobs, monitor real-time worker progress, and download generated certificates.

### Option A: Built-In HTML/JS Studio Dashboard (`/dashboard`)
Served directly by the FastAPI web service without additional server processes.
- **URL:** `http://127.0.0.1:8000/dashboard`
- **Architecture:** Pure Vanilla HTML5, CSS3 (dark glassmorphism, responsive CSS grid), and vanilla JavaScript.
- **Key Features:**
  - Dynamic interactive recipient roster builder (add, edit, remove rows).
  - Drag-and-drop CSV file importer and raw text paste parser.
  - "Load 5 Demo Records" one-click sample loader.
  - Live animated progress bar polling `GET /api/v1/jobs/{job_id}` every 1.2 seconds.
  - Active cluster health indicator tracking `/healthz` (Database & Storage readiness).
  - Direct individual certificate PDF downloads (`/api/v1/certificates/{id}/download`).
  - One-click bulk ZIP archive download (`/api/v1/jobs/{job_id}/download`).
  - Persistent recent jobs history stored in browser `localStorage`.

### Option B: Streamlit Python Web Application (`streamlit_app.py`)
A Python-powered UI ideal for data engineers and quick visual testing.
- **Launch Command:** `streamlit run streamlit_app.py`
- **URL:** `http://localhost:8501`
- **Key Features:**
  - Configurable API Base URL and masked API Key credentials.
  - Native Streamlit interactive data editor (`st.data_editor`) for roster manipulation.
  - CSV file uploader (`st.file_uploader`) with automatic pandas column mapping.
  - Real-time `st.progress` status bar with live polling loop.
  - Metric cards for Total Records, Succeeded, and Failed counts.
  - Direct PDF downloads and bulk ZIP archive download button (`st.download_button`).

---

## Docker Compose Deployment

Spin up the entire production-like cluster—including the FastAPI server, the Celery background worker, and the Redis broker with persistent storage—in a single command:

```bash
docker-compose up --build
```

To stop and remove containers:
```bash
docker-compose down -v
```

Services exposed:
- **FastAPI API Service**: `http://localhost:8000`
- **Interactive Documentation**: `http://localhost:8000/docs`
- **Redis Server**: `localhost:6379` (with AOF data volume persistence)

---

## Running the Test Suite

The test suite validates authentication, rate limiting, Celery worker dispatch, transient backoff retries, storage abstraction safety, Alembic migrations, and health probes.

Run the test suite with full verbosity:

```bash
python -m pytest -v
```

### Test Coverage Highlights (70 Tests / 100% Passing):
```text
============================= test session starts =============================
collected 70 items

tests/test_auth.py ................ [Passes API Key missing, empty, valid, OpenAPI specs]
tests/test_celery.py .............. [Passes Task registration, persistence, backoff retries]
tests/test_certificate_generator.py [Passes PDF generation, typography, long names]
tests/test_endpoints.py ............ [Passes Status polling, pagination, PDF, ZIP & Dashboard]
tests/test_health.py ............... [Passes Healthz probes, DB degradation, storage health]
tests/test_jobs.py ................. [Passes Batch limits, validation, mixed valid/invalid]
tests/test_logging.py .............. [Passes JSON formatting, contextvars correlation IDs]
tests/test_migrations.py ........... [Passes Alembic upgrade and downgrade cycles]
tests/test_processor.py ............ [Passes Atomic worker claim, resumption, retries]
tests/test_rate_limit.py ........... [Passes IP-isolated SlowAPI rate limiting]
tests/test_storage.py .............. [Passes LocalStorage, S3 mock streaming, traversal checks]
tests/test_utils.py ................ [Passes Safe filename generation & path sanitization]

======================== 70 passed, 1 warning in 5.12s ========================
```

---

## API Reference & Workflows

### Interactive OpenAPI Documentation
Once the server is running, navigate to:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc UI:** `http://127.0.0.1:8000/redoc`

> [!TIP]
> In Swagger UI, click the **Authorize** button at the top right and enter your API Key (`dev-secret-key-12345`) to authenticate interactive requests.

---

### 1. Submit a Bulk Certificate Job

Submit a batch of certificate recipients. Returns `202 Accepted` immediately.

- **Endpoint:** `POST /api/v1/jobs/`
- **Headers:** `X-API-Key: dev-secret-key-12345`, `Content-Type: application/json`
- **Rate Limit:** 5 requests / minute per IP

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/" \
  -H "X-API-Key: dev-secret-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "course_name": "Full Stack Cloud Architecture",
    "issue_date": "2026-10-15",
    "recipients": [
      {
        "name": "Jane Doe",
        "email": "jane.doe@example.com"
      },
      {
        "name": "Alex Johnson",
        "email": "alex.j@example.com"
      }
    ]
  }'
```

#### Response (`202 Accepted`):
```json
{
  "job_id": "c7a84e62-2b6d-4720-9498-8ec349a3e211",
  "status": "PENDING",
  "total_records": 2,
  "successful_records": 0,
  "failed_records": 0,
  "created_at": "2026-10-13T15:45:00.000Z",
  "updated_at": "2026-10-13T15:45:00.000Z"
}
```

---

### 2. Poll Job Status & Progress

Check the real-time progress of a submitted job.

- **Endpoint:** `GET /api/v1/jobs/{job_id}`
- **Headers:** `X-API-Key: dev-secret-key-12345`

```bash
curl "http://127.0.0.1:8000/api/v1/jobs/c7a84e62-2b6d-4720-9498-8ec349a3e211" \
  -H "X-API-Key: dev-secret-key-12345"
```

#### Response (`200 OK`):
```json
{
  "job_id": "c7a84e62-2b6d-4720-9498-8ec349a3e211",
  "status": "COMPLETED",
  "total_records": 2,
  "successful_records": 2,
  "failed_records": 0,
  "created_at": "2026-10-13T15:45:00.000Z",
  "updated_at": "2026-10-13T15:45:02.120Z"
}
```

---

### 3. List Generated Certificates (Paginated)

Retrieve detailed records for individual recipients within a job.

- **Endpoint:** `GET /api/v1/jobs/{job_id}/certificates?page=1&page_size=50`
- **Headers:** `X-API-Key: dev-secret-key-12345`

```bash
curl "http://127.0.0.1:8000/api/v1/jobs/c7a84e62-2b6d-4720-9498-8ec349a3e211/certificates?page=1&page_size=50" \
  -H "X-API-Key: dev-secret-key-12345"
```

#### Response (`200 OK`):
```json
{
  "total": 2,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": "e4f8d390-1c94-4d61-b51e-61c0f49f4aa2",
      "job_id": "c7a84e62-2b6d-4720-9498-8ec349a3e211",
      "recipient_name": "Jane Doe",
      "recipient_email": "jane.doe@example.com",
      "status": "SUCCESS",
      "file_path": "certificates/c7a84e62-2b6d-4720-9498-8ec349a3e211/e4f8d390-1c94-4d61-b51e-61c0f49f4aa2.pdf",
      "created_at": "2026-10-13T15:45:00.000Z"
    }
  ]
}
```

---

### 4. Download a Single Certificate

Stream a generated PDF certificate directly to your local file.

- **Endpoint:** `GET /api/v1/certificates/{certificate_id}/download`
- **Headers:** `X-API-Key: dev-secret-key-12345`

```bash
curl -O -J "http://127.0.0.1:8000/api/v1/certificates/e4f8d390-1c94-4d61-b51e-61c0f49f4aa2/download" \
  -H "X-API-Key: dev-secret-key-12345"
```

---

### 5. Download All Certificates as ZIP Archive

Stream a consolidated ZIP archive containing all successfully generated certificates for a job.

- **Endpoint:** `GET /api/v1/jobs/{job_id}/download`
- **Headers:** `X-API-Key: dev-secret-key-12345`

```bash
curl -O -J "http://127.0.0.1:8000/api/v1/jobs/c7a84e62-2b6d-4720-9498-8ec349a3e211/download" \
  -H "X-API-Key: dev-secret-key-12345"
```

---

### 6. Readiness & Liveness Probes (`/healthz`)

Public endpoint designed for Kubernetes probes, AWS ALB health checks, and container orchestrators. Requires no API key.

- **Endpoint:** `GET /healthz`

```bash
curl "http://127.0.0.1:8000/healthz"
```

#### Healthy Response (`200 OK`):
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

#### Degraded Response (`503 Service Unavailable`):
```json
{
  "status": "unhealthy",
  "checks": {
    "database": {
      "status": "down",
      "error": "could not connect to server: Connection refused"
    },
    "storage": {
      "status": "up",
      "backend": "s3"
    }
  }
}
```

---

## Configuration Reference

All settings can be configured via environment variables or a `.env` file:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `API_KEY` | `dev-secret-key-12345` | Master secret key required to access protected routes. |
| `API_KEY_NAME` | `X-API-Key` | Header name inspected for API key authentication. |
| `RATE_LIMIT_JOBS` | `5/minute` | Rate limit threshold applied to `POST /api/v1/jobs/`. |
| `DATABASE_URL` | `sqlite:///./certificates.sqlite` | SQLAlchemy database connection URI (supports PostgreSQL). |
| `STORAGE_TYPE` | `local` | Active storage backend: `local` or `s3`. |
| `STORAGE_DIR` | `./storage` | Directory path for storing files when `STORAGE_TYPE=local`. |
| `S3_BUCKET_NAME` | `certificates` | Target S3 or MinIO bucket name when `STORAGE_TYPE=s3`. |
| `S3_ENDPOINT_URL` | `None` | Custom S3 endpoint URL (e.g. `http://minio:9000` for MinIO). |
| `S3_ACCESS_KEY` | `None` | AWS or MinIO access key credential. |
| `S3_SECRET_KEY` | `None` | AWS or MinIO secret key credential. |
| `S3_REGION` | `us-east-1` | AWS S3 region name. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker and connection URI. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker URL for queuing background tasks. |
| `CELERY_RESULT_BACKEND`| `redis://localhost:6379/0`| Celery backend for task execution results. |
| `MAX_BATCH_SIZE` | `1000` | Maximum number of recipients allowed per job submission. |
| `CERT_MAX_RETRIES` | `3` | Maximum retry attempts for transient PDF rendering errors. |
| `CERT_RETRY_BACKOFF_BASE` | `0.5` | Exponential backoff multiplier base (in seconds). |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## Project Directory Layout

```text
Bulk Certificate Generator/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── certificates.py       # Certificate querying & streaming downloads
│   │       └── jobs.py               # Job submission, status polling, ZIP downloads
│   ├── core/
│   │   ├── celery_app.py             # Celery worker initialization & retry configuration
│   │   ├── config.py                 # Pydantic BaseSettings & environment validation
│   │   ├── database.py               # SQLAlchemy engine, session maker & declarative base
│   │   ├── logging.py                # Structlog JSON formatting & context setup
│   │   ├── middleware.py             # CorrelationIdMiddleware (X-Correlation-ID binding)
│   │   ├── rate_limit.py             # SlowAPI limiter keyed by forwarded client IP
│   │   └── security.py               # Header-based API key authentication dependency
│   ├── models/
│   │   ├── certificate.py            # Certificate SQLAlchemy ORM entity
│   │   ├── enums.py                  # JobStatus & CertificateStatus enumerations
│   │   └── job.py                    # Job SQLAlchemy ORM entity with foreign relations
│   ├── schemas/
│   │   ├── certificate.py            # Pydantic schemas for certificate responses
│   │   └── job.py                    # Pydantic request/response schemas for jobs
│   ├── services/
│   │   ├── certificate_generator.py  # ReportLab PDF vector generation logic
│   │   └── storage.py                # Factory pattern: LocalStorage & S3StorageBackend
│   ├── workers/
│   │   └── tasks.py                  # Celery background job worker & retry loops
│   └── main.py                       # FastAPI application entry point, lifespan & probes
├── alembic/
│   ├── versions/                     # Versioned migration revision scripts
│   └── env.py                        # Alembic migration environment runtime
├── storage/                          # Local directory for generated PDFs and ZIPs
├── tests/                            # 68 automated Pytest test cases
│   ├── test_auth.py                  # API key validation tests
│   ├── test_celery.py                # Celery task dispatch and retry tests
│   ├── test_certificate_generator.py # PDF drawing and font boundary tests
│   ├── test_endpoints.py             # HTTP endpoint integration tests
│   ├── test_health.py                # Active /healthz dependency probe tests
│   ├── test_jobs.py                  # Job validation, boundary, and batch tests
│   ├── test_logging.py               # Structlog and correlation ID tracing tests
│   ├── test_migrations.py           # Alembic upgrade/downgrade cycle tests
│   ├── test_processor.py             # Worker claim, failure isolation, resumption tests
│   ├── test_rate_limit.py            # SlowAPI IP rate limiting tests
│   ├── test_storage.py               # Local & S3 storage streaming abstraction tests
│   └── test_utils.py                 # Security path traversal and sanitization tests
├── .env.example                      # Production-ready environment variable template
├── Dockerfile                        # Multi-stage lightweight Python container image
├── docker-compose.yml                # Multi-service stack (API + Worker + Redis AOF)
├── requirements.txt                  # Locked production dependencies
├── alembic.ini                       # Alembic CLI migration configuration
└── README.md                         # Portfolio-grade documentation
```

---

## Production Roadmap

- [x] Decouple synchronous PDF generation with Celery & Redis task queues.
- [x] Local & Cloud S3 storage abstraction with zero-memory chunked streaming.
- [x] Structured JSON logging with contextvars distributed correlation tracing.
- [x] Active readiness & liveness probes (`/healthz`) for container orchestrators.
- [x] IP-isolated rate limiting and API key authentication.
- [x] Version-controlled database schema migrations with Alembic.
- [ ] **Client Idempotency Keys:** Support `Idempotency-Key` headers on `POST /api/v1/jobs/` to prevent duplicate submissions from retried requests.
- [ ] **Observability & Metrics:** Export Prometheus metrics (`/metrics`) and deploy Flower for real-time Celery worker monitoring.
- [ ] **Webhook Notifications:** Webhook callbacks notifying client systems when bulk jobs complete.
