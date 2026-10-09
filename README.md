# Bulk Certificate Generator API

An asynchronous, robust backend API designed to handle bulk generation of personalized PDF certificates.

## Overview
This API allows clients to submit large batches of recipients. It processes the certificate generation (via ReportLab) in the background so the client isn't blocked. It handles partial failures gracefully—one invalid recipient will not prevent the rest of the batch from succeeding.

## Tech Stack
- **Framework:** FastAPI
- **Database:** SQLite (Default, SQLAlchemy ORM used for easy PostgreSQL migration)
- **PDF Generation:** ReportLab
- **Validation:** Pydantic
- **Testing:** Pytest

## Setup & Running Locally (Recommended)

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
4. **Run the Application:**
   ```bash
   uvicorn app.main:app --reload
   ```
   The API will be available at `http://127.0.0.1:8000`. Navigating to the root URL will automatically redirect you to the interactive API documentation at `http://127.0.0.1:8000/docs`.

## Running with Docker

Docker files are provided for convenience but have not been tested on my machine; the primary supported setup is the local Python virtual environment.

You can also run the application using Docker Compose:
```bash
docker-compose up --build
```

## Running Tests
To run the automated test suite, ensure your virtual environment is activated and run:
```bash
python -m pytest
```

## Example `curl` Requests

*(Note: Replace `{job_id}` and `{certificate_id}` with the actual UUIDs returned by the API).*

### 1. Submit a Job
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/" \
     -H "Content-Type: application/json" \
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
curl "http://127.0.0.1:8000/api/v1/jobs/{job_id}"
```

### 3. Retrieve Paginated Certificates
```bash
curl "http://127.0.0.1:8000/api/v1/jobs/{job_id}/certificates?page=1&page_size=50"
```

### 4. Download a Single Certificate PDF
```bash
curl -O -J "http://127.0.0.1:8000/api/v1/certificates/{certificate_id}/download"
```

### 5. Download ZIP of All Successful Certificates
```bash
curl -O -J "http://127.0.0.1:8000/api/v1/jobs/{job_id}/download"
```

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
- **Background vs. Synchronous Processing:** PDF generation is a CPU-bound and I/O-heavy task. Generating 1,000 PDFs synchronously would block the HTTP request, leading to timeouts and a poor user experience. Background processing immediately returns a `202 Accepted` and allows the client to poll for progress.
- **Per-Certificate Failure Isolation:** If 999 recipients are valid but 1 has a malformed email, the system shouldn't reject the entire batch. The system uses a permissive API strategy: it accepts the batch, and the worker isolates validation/generation failures on a per-certificate basis inside a `try/except` block, ensuring the rest of the batch succeeds.
- **Atomic Job Claims & Counters:** The background worker uses a database `UPDATE ... WHERE status = 'PENDING'` claim system to prevent race conditions if multiple workers run. It also uses atomic SQL expressions (e.g., `succeeded = succeeded + 1`) to update job progress safely rather than relying on Python memory increments.
- **Temp-File ZIP Streaming:** To prevent Out-Of-Memory (OOM) errors on large jobs, the ZIP download endpoint streams the contents directly from a safely generated temporary file (`tempfile.NamedTemporaryFile`) on disk rather than holding thousands of PDFs in memory. The temp file is automatically deleted via a FastAPI `BackgroundTask` upon completion.
- **Stuck-Job Recovery:** On API startup, a routine runs to scan the database for jobs that have been stuck in `PROCESSING` for over an hour. These are defensively marked as `FAILED`. Re-queueing them automatically is avoided to prevent corrupting state or triggering infinite crash-loops without strict idempotency guarantees.

## Known Limitations / Future Scope

If this were deployed to a highly available production environment, I would make the following improvements:
1. **Task Queue (Celery/Redis):** Replace `FastAPI.BackgroundTasks` with Celery and a message broker. `BackgroundTasks` run in the API memory space, meaning if the API restarts, actively queued tasks are lost. Celery provides persistence, distributed scaling, and retry semantics.
2. **Object Storage (AWS S3):** Replace local disk storage with cloud object storage. Local storage does not scale horizontally (if the API is deployed across multiple stateless containers, they won't share the same disk). 
3. **Idempotency Keys:** Implement idempotency keys for the POST endpoint to prevent accidental duplicate submissions from clients experiencing network hiccups.
4. **Monitoring:** Add Prometheus metrics to track PDF generation latency, worker failure rates, and active job counts to maintain system health visibility.
5. **Retries:** For transient errors (e.g., temporary storage write failures), background workers should implement an exponential backoff retry mechanism on a per-certificate basis before marking it as permanently `FAILED`.
