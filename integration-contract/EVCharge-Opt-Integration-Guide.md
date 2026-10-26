# EVCharge-Predict <-> EVCharge-Opt Integration Guide

**Document Version:** 1.0
**Specification Date:** October 26, 2026
**Predictor Service Base URL:** `https://evcharge-predict.onrender.com`
**Optimizer Client Application URLs:**
- Web Frontend: `https://evcharge-opt.onrender.com`
- Backend API Service: `https://evcharge-opt-api.onrender.com`

---

## 1. System Roles & Integration Boundaries

- **EVCharge-Predict (Predictor):** Generates 6-hour recursive demand predictions (arrival counts and cumulative energy kWh per 60-minute interval) for canonical stations. Ingests optimizer allocation decisions and derives operational demand envelopes.
- **EVCharge-Opt (Optimizer):** Consumes forecast envelopes, schedules chargers/slots under physical grid limitations, and submits allocation results back to EVCharge-Predict.
- **Storage Independence:** Each system maintains an isolated data store. EVCharge-Predict never accesses EVCharge-Opt databases, and EVCharge-Opt accesses EVCharge-Predict exclusively via HTTPS REST API.
- **Partner Mock Mode Agreement:** EVCharge-Opt operates in mock mode until live end-to-end verification, schema alignment, and authoritative station inventory confirmations are completed.

---

## 2. Authentication, Transport & Security

### 2.1. Bearer Token Enforcement
- **Protected Endpoints:** All `/api/v1/forecasts*`, `/api/v1/feedback*`, `/api/v1/stations*`, and `/api/v1/sessions*` endpoints require a Bearer token:
  ```http
  Authorization: Bearer <API_AUTH_TOKEN>
  ```
- **Failure Responses:**
  - Missing Authorization Header: `HTTP 401 Unauthorized` (`WWW-Authenticate: Bearer`).
  - Invalid / Mismatched Token: `HTTP 403 Forbidden` (`{"detail": "Invalid or expired API authorization token."}`).
  - Production Guard: If `APP_ENV=production` and `API_AUTH_TOKEN` is unset or default, the application aborts startup (fail-closed).
- **Public Operational Endpoints (Auth Exempt):**
  - `GET /healthz` (and `GET /api/v1/healthz`)
  - `GET /readyz` (and `GET /api/v1/readyz`)

### 2.2. Cross-Origin Resource Sharing (CORS)
- **Backend API Calls (`evcharge-opt-api` -> `evcharge-predict`):** CORS does **not** apply to direct server-to-server HTTP requests (e.g., Python `httpx`, Node.js `fetch`/`axios`).
- **Browser Client Calls (`evcharge-opt` UI -> `evcharge-predict`):**
  - Browser calls require the origin to be explicitly registered in `FRONTEND_ORIGIN`:
    ```env
    FRONTEND_ORIGIN="https://evcharge-opt.onrender.com"
    ```
  - Multiple origins can be comma-separated. Wildcards (`*`) are disallowed with credentialed requests in production.

### 2.3. Request Tracing & Correlation
- Callers may send `X-Request-ID` or `X-Correlation-ID` containing 8â€“64 alphanumeric characters, underscores, or hyphens.
- Unsafe strings are sanitized and replaced with a UUIDv4.
- All responses reflect the active ID in the `X-Request-ID` response header.

---

## 3. Station Inventory & Canonical Mapping

All forecast and feedback endpoints operate strictly on **canonical station IDs** (`ST-xxx`).

| Canonical Station ID | Hardware / Source Station ID | Status in Repository | Authoritative Hardware Confirmation Status |
| :--- | :--- | :--- | :--- |
| **`ST-001`** | `1-39-139-650` | Present in `station_mapping.json` | **Unconfirmed against physical hardware.** Repository mapping and synthetic fixtures establish code association only; no physical site manifest or hardware commissioning document exists in repository. |
| **`ST-002`** | `1-39-139-651` | Present in `station_mapping.json` | **Unconfirmed against physical hardware.** Repository mapping and synthetic fixtures establish code association only; no physical site manifest or hardware commissioning document exists in repository. |
| **`ST-003`** | `1-39-139-652` | Present in `station_mapping.json` | **Provisional & Unconfirmed.** Authoritative hardware proof (serial number, nameplate, or utility interconnection log) is required before genuine charging sessions are ingested. |

> [!WARNING]
> No authoritative physical charger registry or commissioning log exists in this repository. All mappings reflect internal software dictionary mappings. Physical hardware identity must be validated with the site operator before relying on predictions for live charging equipment.

---

## 4. Historical Data Sufficiency Requirements

- **Forecasting Prerequisite:** The model requires past session observations to build rolling lag features.
- **Rule:** The 21 days immediately preceding `forecast_start` (`[forecast_start - 21 days, forecast_start)`) must contain at least **5 historical charging sessions** for each requested station.
- **Failure Behavior:** If any requested station has fewer than 5 observations, `POST /api/v1/forecasts` returns `HTTP 400 Bad Request` (`InsufficientHistoryError`).
- **Safe Pre-Flight Check:** EVCharge-Opt can verify data sufficiency without retrieving private session records by calling:
  ```http
  GET /api/v1/sessions?station_id=ST-001&start_time=2026-10-05T12:00:00Z&limit=5
  ```
  If fewer than 5 items return, history is insufficient to run a forecast.

---

## 5. API Endpoint Specifications

*(All JSON payloads below are explicitly labeled as **Illustrative Sample Payloads** conforming to implementation schemas. No production records were fabricated).*

### 5.1. Generate 6-Hour Baseline Forecast
`POST /api/v1/forecasts`

Generates recursive hourly predictions across 6 consecutive intervals for the specified canonical stations.

- **Request Fields (`ForecastCreateRequest`):**
  - `scenario_id` (`string`, required, 1â€“128 chars): Unique simulation or batch identifier.
  - `station_ids` (`list[string]`, required): List of canonical IDs matching `^ST-`. No duplicates.
  - `forecast_start` (`string`, required): Timezone-aware UTC ISO 8601 string (`...Z`). **Must be aligned to an exact UTC hour** (`minute=0, second=0, microsecond=0`).
  - `interval_minutes` (`integer`, optional, default: `60`): Must be `60` for v1.0.
  - `horizon_intervals` (`integer`, optional, default: `6`): Must be `6` for v1.0.

#### Illustrative Request Example:
```json
{
  "scenario_id": "scenario_20261026_opt_run_01",
  "station_ids": ["ST-001", "ST-002", "ST-003"],
  "forecast_start": "2026-10-26T12:00:00Z",
  "interval_minutes": 60,
  "horizon_intervals": 6
}
```

#### Illustrative Response (`HTTP 201 Created` - `ForecastCreateResponse`):
```json
{
  "contract_version": "1.0",
  "forecast_id": "fcst_7a8b9c0d1e2f",
  "scenario_id": "scenario_20261026_opt_run_01",
  "status": "completed",
  "demand_type": "baseline",
  "generated_at": "2026-10-26T11:20:00Z",
  "interval_minutes": 60,
  "horizon_intervals": 6,
  "forecast_url": "/api/v1/forecasts/fcst_7a8b9c0d1e2f"
}
```

#### Status & Error Codes:
- `HTTP 201 Created`: Forecast generated and persisted.
- `HTTP 400 Bad Request`: `InsufficientHistoryError` (< 5 sessions in preceding 21 days for a station).
- `HTTP 404 Not Found`: Station ID does not exist in the database.
- `HTTP 422 Unprocessable Entity`: Unaligned `forecast_start` (non-zero minutes/seconds), invalid format, or non-ST station ID.
- `HTTP 503 Service Unavailable`: ML models or manifest unavailable in memory.

---

### 5.2. Retrieve Baseline Forecast Detail
`GET /api/v1/forecasts/{forecast_id}`

Retrieves the 6-interval hourly predictions for all stations in the forecast.

- **Path Parameter:** `forecast_id` (`string`, e.g., `fcst_7a8b9c0d1e2f`).

#### Illustrative Response (`HTTP 200 OK` - `ForecastDetailRead`):
```json
{
  "contract_version": "1.0",
  "forecast_id": "fcst_7a8b9c0d1e2f",
  "scenario_id": "scenario_20261026_opt_run_01",
  "generated_at": "2026-10-26T11:20:00Z",
  "horizon": {
    "start": "2026-10-26T12:00:00Z",
    "end": "2026-10-26T18:00:00Z",
    "interval_minutes": 60,
    "interval_count": 6
  },
  "demand_type": "baseline",
  "stations": [
    {
      "station_id": "ST-001",
      "intervals": [
        {
          "interval_start": "2026-10-26T12:00:00Z",
          "interval_end": "2026-10-26T13:00:00Z",
          "predicted_arrivals": 2,
          "predicted_energy_kwh": 34.500
        },
        {
          "interval_start": "2026-10-26T13:00:00Z",
          "interval_end": "2026-10-26T14:00:00Z",
          "predicted_arrivals": 1,
          "predicted_energy_kwh": 18.250
        },
        {
          "interval_start": "2026-10-26T14:00:00Z",
          "interval_end": "2026-10-26T15:00:00Z",
          "predicted_arrivals": 1,
          "predicted_energy_kwh": 16.800
        },
        {
          "interval_start": "2026-10-26T15:00:00Z",
          "interval_end": "2026-10-26T16:00:00Z",
          "predicted_arrivals": 3,
          "predicted_energy_kwh": 48.100
        },
        {
          "interval_start": "2026-10-26T16:00:00Z",
          "interval_end": "2026-10-26T17:00:00Z",
          "predicted_arrivals": 2,
          "predicted_energy_kwh": 31.000
        },
        {
          "interval_start": "2026-10-26T17:00:00Z",
          "interval_end": "2026-10-26T18:00:00Z",
          "predicted_arrivals": 1,
          "predicted_energy_kwh": 14.750
        }
      ]
    }
  ],
  "model": {
    "model_version": "1.0",
    "training_data_type": "synthetic",
    "scikit_learn_version": "1.9.1",
    "training_data_fingerprint": "manifest_synthetic_fixtures_v1"
  }
}
```

- **Semantics:**
  - `predicted_arrivals` (`int`, $\ge 0$): Number of distinct charging sessions expected to plug in during the interval.
  - `predicted_energy_kwh` (`float`, $\ge 0.0$): Total energy demanded by sessions starting in the interval.
  - Interval representations are semi-open bounds `[interval_start, interval_end)`.

---

### 5.3. Ingest Optimizer Allocation Feedback
`POST /api/v1/feedback`

Submits allocation decisions from EVCharge-Opt. Persists feedback and atomically computes derived adjusted operational demand.

- **Request Fields (`FeedbackCreateRequest`):**
  - `contract_version` (`string`, default: `"1.0"`).
  - `allocation_run_id` (`string`, required, 1â€“128 chars): Unique run ID generated by EVCharge-Opt.
  - `forecast_id` (`string`, required): Originating forecast ID.
  - `scenario_id` (`string`, required): Must match originating forecast scenario.
  - `submitted_at` (`string`, required): Timezone-aware UTC ISO 8601 string (`...Z`).
  - `optimizer_version` (`string`, optional): Optimizer build/version identifier.
  - `stations` (`list`, required): List of stations with intervals matching the originating forecast intervals.

#### Illustrative Request Example:
```json
{
  "contract_version": "1.0",
  "allocation_run_id": "opt_run_20261026_001",
  "forecast_id": "fcst_7a8b9c0d1e2f",
  "scenario_id": "scenario_20261026_opt_run_01",
  "submitted_at": "2026-10-26T11:25:00Z",
  "optimizer_version": "opt-core-2.4.1",
  "stations": [
    {
      "station_id": "ST-001",
      "intervals": [
        {
          "interval_start": "2026-10-26T12:00:00Z",
          "interval_end": "2026-10-26T13:00:00Z",
          "allocated_energy_kwh": 38.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 0.0
        },
        {
          "interval_start": "2026-10-26T13:00:00Z",
          "interval_end": "2026-10-26T14:00:00Z",
          "allocated_energy_kwh": 15.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 3.250
        },
        {
          "interval_start": "2026-10-26T14:00:00Z",
          "interval_end": "2026-10-26T15:00:00Z",
          "allocated_energy_kwh": 16.800,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 0.0
        },
        {
          "interval_start": "2026-10-26T15:00:00Z",
          "interval_end": "2026-10-26T16:00:00Z",
          "allocated_energy_kwh": 50.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 2.500
        },
        {
          "interval_start": "2026-10-26T16:00:00Z",
          "interval_end": "2026-10-26T17:00:00Z",
          "allocated_energy_kwh": 31.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 0.0
        },
        {
          "interval_start": "2026-10-26T17:00:00Z",
          "interval_end": "2026-10-26T18:00:00Z",
          "allocated_energy_kwh": 14.750,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 0.0
        }
      ]
    }
  ]
}
```

#### Idempotency Behavior:
1. **Initial Submission (`HTTP 201 Created`):**
   ```json
   {
     "contract_version": "1.0",
     "feedback_id": "fbk_1a2b3c4d5e6f",
     "allocation_run_id": "opt_run_20261026_001",
     "forecast_id": "fcst_7a8b9c0d1e2f",
     "scenario_id": "scenario_20261026_opt_run_01",
     "status": "accepted",
     "is_duplicate": false,
     "received_at": "2026-10-26T11:25:01Z",
     "feedback_url": "/api/v1/feedback/fbk_1a2b3c4d5e6f"
   }
   ```
2. **Identical Retry (`HTTP 200 OK`):**
   When `allocation_run_id` matches an existing record and the payload SHA-256 hash matches identically: returns `is_duplicate: true` with the original `feedback_id`.
3. **Conflicting Payload (`HTTP 409 Conflict`):**
   When `allocation_run_id` was already submitted, but any payload field differs:
   `{"detail": "Allocation run '...' was already submitted with different content. Reusing the same run identifier with modified data is prohibited."}`

---

### 5.4. Retrieve Feedback Metadata
`GET /api/v1/feedback/{feedback_id}`

Retrieves submission metadata for a previously ingested allocation run.

#### Illustrative Response (`HTTP 200 OK` - `FeedbackDetailRead`):
```json
{
  "contract_version": "1.0",
  "feedback_id": "fbk_1a2b3c4d5e6f",
  "allocation_run_id": "opt_run_20261026_001",
  "forecast_id": "fcst_7a8b9c0d1e2f",
  "scenario_id": "scenario_20261026_opt_run_01",
  "status": "accepted",
  "optimizer_version": "opt-core-2.4.1",
  "submitted_at": "2026-10-26T11:25:00Z",
  "received_at": "2026-10-26T11:25:01Z"
}
```

---

### 5.5. Retrieve Feedback-Adjusted Operational Demand
`GET /api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id=...`

Retrieves the derived operational demand envelope comparing baseline forecast values against accepted allocation results.

- **Query Parameter:** `feedback_id` (`string`, required).
- **Calculation Formula (`v1-heuristic-operational-envelope`):**
  $$\text{adjusted\_operational\_demand\_kwh} = \max(\text{baseline\_predicted\_energy\_kwh}, \text{allocated\_energy\_kwh})$$
  - `baseline_arrivals` are strictly preserved without modification.
  - `adjustment_status` returns `"adjusted"` if allocated > baseline, `"unchanged"` if allocated $\le$ baseline, or `"insufficient_data"` if allocated energy was null.
  - The baseline forecast remains permanently immutable.

> [!WARNING]
> **Heuristic Limitation:** The adjusted operational demand envelope represents an operational heuristic taking $\max(\text{baseline}, \text{allocated})$. It reflects optimizer scheduling decisions under grid limits, **not verified ground-truth physical driver demand**.

#### Illustrative Response (`HTTP 200 OK` - `AdjustedDemandResponse`):
```json
{
  "contract_version": "1.0",
  "forecast_id": "fcst_7a8b9c0d1e2f",
  "scenario_id": "scenario_20261026_opt_run_01",
  "feedback_id": "fbk_1a2b3c4d5e6f",
  "allocation_run_id": "opt_run_20261026_001",
  "demand_type": "feedback-adjusted-operational",
  "adjustment_policy_version": "v1-heuristic-operational-envelope",
  "policy_description": "Operational demand envelope taking max(baseline_predicted_energy_kwh, allocated_energy_kwh). Arrivals strictly preserved from baseline without fabrication.",
  "policy_limitations": "Allocated energy reflects optimizer decisions under physical and grid constraints, not unconstrained physical demand. This envelope does not represent verified ground-truth physical driver demand.",
  "computed_at": "2026-10-26T11:25:01Z",
  "stations": [
    {
      "station_id": "ST-001",
      "intervals": [
        {
          "interval_start": "2026-10-26T12:00:00Z",
          "interval_end": "2026-10-26T13:00:00Z",
          "baseline_arrivals": 2,
          "baseline_energy_kwh": 34.500,
          "allocated_energy_kwh": 38.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 0.0,
          "adjusted_operational_demand_kwh": 38.000,
          "adjustment_status": "adjusted"
        },
        {
          "interval_start": "2026-10-26T13:00:00Z",
          "interval_end": "2026-10-26T14:00:00Z",
          "baseline_arrivals": 1,
          "baseline_energy_kwh": 18.250,
          "allocated_energy_kwh": 15.000,
          "available_capacity_kw": 50.0,
          "reported_unmet_demand_kwh": 3.250,
          "adjusted_operational_demand_kwh": 18.250,
          "adjustment_status": "unchanged"
        }
      ]
    }
  ]
}
```

---

### 5.6. Query Charging Stations
`GET /api/v1/stations`

Returns registered charging stations and their canonical identifiers.

- **Query Parameters:**
  - `site_id` (`string`, optional): Filters stations by site (e.g. `caltech`).

#### Illustrative Response (`HTTP 200 OK` - `List[StationRead]`):
```json
[
  {
    "id": 1,
    "station_id": "ST-001",
    "source_station_id": "1-39-139-650",
    "site_id": "caltech",
    "created_at": "2026-10-24T20:00:00Z",
    "updated_at": "2026-10-24T20:00:00Z"
  },
  {
    "id": 2,
    "station_id": "ST-002",
    "source_station_id": "1-39-139-651",
    "site_id": "caltech",
    "created_at": "2026-10-24T20:00:00Z",
    "updated_at": "2026-10-24T20:00:00Z"
  }
]
```

---

### 5.7. Query Historical Sessions (Pre-flight Data Sufficiency Check)
`GET /api/v1/sessions`

Queries historical charging sessions with pagination and station filtering.

- **Query Parameters:**
  - `station_id` (`string`, optional): Canonical station identifier (e.g. `ST-001`).
  - `start_time` (`string`, optional): UTC ISO 8601 timestamp (`connection_time >= start_time`).
  - `end_time` (`string`, optional): UTC ISO 8601 timestamp (`connection_time <= end_time`).
  - `limit` (`integer`, optional, default: `50`, min: `1`, max: `500`): Maximum records to return.
  - `offset` (`integer`, optional, default: `0`): Pagination offset.

#### Illustrative Response (`HTTP 200 OK` - `List[ChargingSessionRead]`):
```json
[
  {
    "id": 101,
    "source_session_id": "session_sample_001",
    "station_id": "ST-001",
    "connection_time": "2026-10-15T08:30:00Z",
    "disconnect_time": "2026-10-15T12:45:00Z",
    "kwh_delivered": 28.50,
    "source_site_id": "caltech",
    "source_timezone": "America/Los_Angeles",
    "source_dataset": "acn-data"
  }
]
```

---

## 6. Integration Evidence Matrix

Every workflow in this contract is categorized into one of four verified evidence tiers:

| Workflow / Capability | Evidence Classification | Grounding Code & Test Reference |
| :--- | :--- | :--- |
| **Fail-closed Bearer Authentication** | **Verified by automated tests** | `backend/app/core/security.py:18-67`; `backend/tests/test_end_to_end_integration.py:test_service_to_service_auth_enforcement_and_public_probes` |
| **Forecast Creation (`POST /forecasts`)** | **Verified by automated tests** | `backend/app/api/v1/routes/forecasts.py:29-66`; `backend/tests/test_forecasting_service.py:227-244` |
| **Forecast Retrieval (`GET /forecasts/{id}`)** | **Verified by automated tests** | `backend/app/api/v1/routes/forecasts.py:88-104`; `backend/tests/test_forecasting_service.py:246-259` |
| **Three-Station Simultaneous Forecast** | **Verified by automated tests** | `backend/tests/test_forecasting_service.py:289-343` (`test_recursive_forecasting_three_stations_simultaneously`) |
| **Feedback Submission (`POST /feedback`)** | **Verified by automated tests** | `backend/app/api/v1/routes/feedback.py:30-70`; `backend/tests/test_feedback.py:test_feedback_api_full_http_lifecycle` |
| **Identical-Retry Idempotency (`200 OK`)** | **Verified by automated tests** | `backend/app/services/feedback_service.py:89-110`; `backend/tests/test_feedback.py:65-74` |
| **Conflicting Payload Retry (`409 Conflict`)** | **Verified by automated tests** | `backend/app/services/feedback_service.py:111-116`; `backend/tests/test_feedback.py:75-85` |
| **Adjusted Demand Operational Envelope** | **Verified by automated tests** | `backend/app/services/feedback_service.py:186-215`; `backend/tests/test_feedback.py:25-60` |
| **Baseline Forecast Immutability** | **Verified by automated tests** | `backend/tests/test_feedback.py:test_baseline_forecast_strictly_immutable_after_feedback` |
| **Readiness Probe Failure on Missing Models**| **Verified by automated tests** | `backend/tests/test_health.py:test_readyz_models_unavailable` (returns 503 when models unloaded) |
| **Station & Session Endpoints (`/stations`, `/sessions`)** | **Verified by automated tests** | `backend/tests/test_database_and_ingestion.py:test_api_stations_and_sessions` |
| **Readiness Probe Logic (`/readyz`)** | **Verified by implementation/code** | `backend/app/api/v1/routes/ready.py:15-46` (checks `SELECT 1` and `ModelService.get_instance().is_loaded`) |
| **OpenAPI Schema Consistency** | **Verified by implementation/code** | Extracted directly from FastAPI instance via `get_openapi()` matching active routes |
| **Liveness & Readiness Probes** | **Previously verified against deployed service** | Initial deploy returned HTTP 200 on `/healthz` and `/readyz` probes |
| **Complete Live Forecasting & Feedback Workflow** | **Not yet verified end to end** | Awaiting database migration (`alembic upgrade head`), $\ge 5$ sessions per station, and live partner integration verification |
| **Three-Station Live Integration** | **Not yet verified end to end** | Requires production database setup and confirmed hardware station mapping for ST-003 |
