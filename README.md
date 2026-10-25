# EVCharge-Predict — Electric Vehicle Charging Demand Prediction System

Production-grade machine-learning forecasting system that predicts station-level EV session arrivals and kilowatt-hour energy demand, integrating in a closed feedback loop with **EVCharge-Opt**.

---

## 1. Project Overview & Architecture

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2 (async), Uvicorn (Port `8001`)
- **Data Science / ML:** pandas, NumPy, scikit-learn, joblib
- **Testing:** pytest, pytest-asyncio, HTTPX
- **Database:** PostgreSQL (production on Render) / SQLite async (`sqlite+aiosqlite`) for local dev and testing
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS (Port `5173`)
- **Integration Partner:** EVCharge-Opt (Port `8000`)
- **Dataset Source:** ACN-Data (Caltech/JPL public EV charging dataset)

---

## 2. Directory Structure

```
EVCharge-Predict/
  backend/
    app/
      api/          # Versioned REST endpoints (/api/v1/stations, /sessions, /imports, /healthz)
      core/         # Configuration, logging, settings (pydantic-settings)
      db/           # Database sessions, engine, base model, Alembic migrations
      models/       # SQLAlchemy ORM models (Station, ChargingSession, DatasetImport)
      schemas/      # Pydantic v2 schemas with UTC ISO 8601 validation
      services/     # Ingestion pipeline & persistent station ID mapping
      ml/           # Preprocessors, feature extractors, inference engines (Phase 3)
      main.py       # FastAPI application entrypoint
    migrations/     # Alembic database migrations
    tests/          # Unit & integration test suite with synthetic fixtures
    requirements.txt
  frontend/         # React + TypeScript + Vite + Tailwind CSS
  data/
    raw/            # Raw datasets (excluded from Git)
    processed/      # Processed data and station_mapping.json
  artifacts/        # Serialized ML models (.joblib)
  scripts/          # ingest_dataset.py CLI ingestion pipeline
  integration-contract/
    examples/       # JSON payloads for EVCharge-Opt interoperability
    README.md       # Canonical integration specification
  docs/             # Architectural documentation and reviews
  .env.example      # Environment variable template
  .gitignore        # Excludes venvs, secrets, data, and build outputs
  README.md
```

---

## 3. Database Configuration & Migrations

The database connection is managed asynchronously using SQLAlchemy 2.x and configured via `DATABASE_URL` in `.env`:
- **Production (PostgreSQL):** `postgresql+asyncpg://user:password@host:5432/evcharge_predict`
- **Local Development / Testing (SQLite):** `sqlite+aiosqlite:///evcharge_predict.db`

### Running Migrations (Alembic)
```powershell
# From project root:
cd backend
$env:PYTHONPATH = "."
python -m alembic upgrade head
```

To generate a new migration after model changes:
```powershell
python -m alembic revision --autogenerate -m "describe_change"
```

---

## 4. Dataset Ingestion Pipeline

The repeatable ingestion pipeline lives in `scripts/ingest_dataset.py`.

### Features
1. **Validation:** Checks for valid JSON and extracts session dictionaries under `_items`.
2. **Resilience:** Handles truncated JSON, missing fields, or empty arrays with descriptive errors.
3. **UTC Normalization:** Parses RFC/ISO timestamps and normalizes to UTC with `Z` suffix.
4. **Stable Station Mapping:** Deterministically maps source station strings (e.g., `1-39-139-650`) to canonical identifiers (`ST-001`, `ST-002`) stored in `data/processed/station_mapping.json`.
5. **Deduplication:** Prevents duplicate imports based on `source_session_id`.
6. **Audit Tracking:** Records batch imports in `dataset_imports` with counts of read, inserted, skipped, and rejected records.

### Running Ingestion
```powershell
# Ingest an ACN-Data JSON file:
$env:PYTHONPATH = "backend"
python scripts/ingest_dataset.py "data/raw/acndata_sessions.json"

# Ingest in dry-run mode (validates without writing to database):
python scripts/ingest_dataset.py "data/raw/acndata_sessions.json" --dry-run
```

---

## 5. Dataset Licensing & Source Considerations

- **Official Source:** [Caltech ACN-Data Portal](https://ev.caltech.edu/dataset)
- **License / Terms:** ACN-Data is provided by the California Institute of Technology for non-commercial academic and research use. Cite the ACN-Data paper when publishing results.
- **Data Boundary:** EVCharge-Predict maintains its own database. It never accesses EVCharge-Opt's database directly.

---

## 6. Running Tests

```powershell
cd "d:\ADV PY\EVCharge-Predict"
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -v
```

Automated tests cover:
- Schema validation (positive energy, valid timestamps, disconnect >= connect).
- Deterministic station mapping persistence.
- Full ingestion pipeline (success, duplicates, dry-run, rejection reasons, truncated JSON).
- REST API queries (`/api/v1/stations`, `/api/v1/sessions`).
- Health endpoints (`/healthz`, `/api/v1/healthz`).

---

## 7. Model Training Pipeline (Phase 3)

The Phase 3 ML pipeline (`scripts/train_models.py`) performs station-level hourly demand aggregation, past-only feature extraction, chronological train/validation/test splitting (70%/15%/15%), baseline benchmarking, and Random Forest regression.

### Running Model Training
```powershell
# From database
$env:PYTHONPATH = "backend"
python scripts/train_models.py --source database --output-dir artifacts/models

# From a processed dataset export
python scripts/train_models.py --source backend/tests/fixtures/synthetic_14day_sessions.json --output-dir artifacts/models

# Dry-run validation (runs pipeline without saving artifacts)
python scripts/train_models.py --source backend/tests/fixtures/synthetic_14day_sessions.json --dry-run
```

Artifacts generated under `artifacts/models/`:
- `arrival_model.joblib`: Serialized arrival regressor.
- `energy_model.joblib`: Serialized energy regressor.
- `manifest.json`: Training manifest containing timestamps, splits, feature names, parameters, and metrics.
- `evaluation_report.md`: Human-readable evaluation report with per-station performance.

---

## 8. Forecast API & EVCharge-Opt Integration (Phase 4)

Phase 4 exposes the agreed contract version `1.0` endpoints under `/api/v1` for generating and retrieving 6-hour forecasts.

### Forecast Endpoints
- `GET /healthz` & `GET /api/v1/healthz`: Liveness check.
- `GET /readyz` & `GET /api/v1/readyz`: Readiness check verifying database connectivity and model status.
- `POST /api/v1/forecasts`: Triggers recursive multi-step forecasting for requested station IDs over 6 hourly intervals.
- `GET /api/v1/forecasts/{forecast_id}`: Retrieves complete stored forecast and interval predictions.
- `GET /api/v1/forecasts/latest?scenario_id=...`: Retrieves newest completed baseline forecast for scenario.

### Example Request (`POST /api/v1/forecasts`)
```json
{
  "scenario_id": "scenario_demo_001",
  "station_ids": ["ST-001", "ST-002", "ST-003"],
  "forecast_start": "2026-10-25T09:00:00Z",
  "interval_minutes": 60,
  "horizon_intervals": 6
}
```

### Starting the Server
```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
OpenAPI documentation: **http://127.0.0.1:8001/docs**

---

## 9. Allocation Feedback & Operational Demand (Phase 5)

Phase 5 ingests allocation feedback from **EVCharge-Opt** and computes a separately stored, versioned operational demand envelope without altering baseline forecasts or retraining models.

### Endpoints
- `POST /api/v1/feedback`: Submits optimizer allocation feedback. Enforces deterministic idempotency using `allocation_run_id` and SHA-256 payload hashing (`201 Created` for new, `200 OK` for duplicate identical, `409 Conflict` for modified payload with reused run ID).
- `GET /api/v1/feedback/{feedback_id}`: Retrieves stored feedback metadata and validation status.
- `GET /api/v1/feedback?forecast_id=...&scenario_id=...`: Lists feedback runs for a forecast or scenario.
- `GET /api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id=...`: Retrieves station-level operational demand envelope comparing baseline predictions, allocated energy, and derived operational demand.

### Policy v1: Heuristic Operational Envelope
- **Version:** `v1-heuristic-operational-envelope`
- **Formula:** $\text{adjusted\_operational\_demand\_kwh} = \max(\text{baseline\_energy\_kwh},\, \text{allocated\_energy\_kwh})$
- **Baseline Preservation:** Baseline arrivals (`predicted_arrivals`) and energy (`predicted_energy_kwh`) remain strictly immutable in `forecast_intervals`.
- **Limitation:** Allocated energy reflects optimizer decisions under physical and grid constraints, not unconstrained physical demand. This envelope does not claim to represent verified ground-truth physical driver demand.
- **Unmet Demand:** Only reported if explicitly provided by optimizer (`reported_unmet_demand_kwh`).

---

## 10. Security, Authentication & Observability (Phase 6)

Phase 6 hardens the service for production readiness and safe inter-service integration with EVCharge-Opt.

### Service-to-Service Authentication
- **Bearer Token Enforcement:** Protected endpoints under `/api/v1` require `Authorization: Bearer <API_AUTH_TOKEN>`.
- **Production Fail-Closed:** If `APP_ENV=production` and `API_AUTH_TOKEN` is unset or default, the application **fails closed on startup** and prevents unauthenticated execution.
- **Local Sandbox Mode:** If `APP_ENV=development` and `API_AUTH_TOKEN` is unset, requests are permitted for local development with an explicit log warning.
- **Public Operational Probes:** `GET /healthz` and `GET /readyz` are exempt from token authentication to allow orchestrators (Docker, Kubernetes, Render) to probe liveness and readiness safely.
- **Documentation Protection:** OpenAPI docs (`/docs`, `/openapi.json`) can be disabled in production by setting `ENABLE_DOCS=false`.

### Safe Observability & Request Correlation
- Callers may provide `X-Request-ID` or `X-Correlation-ID` (8 to 64 alphanumeric chars).
- Non-conforming or multiline values are sanitized to prevent log injection and replaced with a UUID.
- The canonical `X-Request-ID` is returned on all responses.
- Access logs output structured metadata (`request_id`, `method`, `path`, `status`, `duration_ms`) without logging credentials, tokens, or raw request payloads.

### Rollback Strategy (Production Safeguard)
- **Do NOT unset `API_AUTH_TOKEN` as a rollback strategy.** Unsetting the token in production triggers an intentional startup abort (fail-closed) or re-exposes endpoints.
- If an authorization or release issue arises, roll back the application git release commit or route traffic through a restricted private network boundary while retaining strict token authentication.

---

## 11. Model Provenance & Authentic Data Limitations

- **Current Model Status:** The active model artifacts (`artifacts/models/arrival_model.joblib` and `energy_model.joblib`) were trained on the synthetic 14-day fixture (`synthetic_14day_sessions.json`).
- **Data Disclaimer:** Model forecasts support full integration and contract testing with EVCharge-Opt, but **do not establish real-world predictive accuracy** under authentic EV driver load.
- **Remaining Roadmap for Real-World Accuracy:**
  1. Download authentic Caltech/JPL ACN-Data sessions from `https://ev.caltech.edu/dataset`.
  2. Validate and ingest sessions using `python scripts/ingest_dataset.py --file data/raw/acndata_sessions.json`.
  3. Retrain arrival and energy regressors using `python scripts/train_models.py --source database`.
  4. Perform chronological holdout evaluation and update `evaluation_report.md`.


