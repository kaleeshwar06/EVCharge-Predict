# EVCharge-Predict <-> EVCharge-Opt Integration Contract

**Contract Version:** 1.0  
**Specification Date:** October 2026  
**Status:** Hardened Baseline (Phase 6)

## 1. Scope & System Roles

- **EVCharge-Predict (Predictor):** Forecasts station-level EV session arrivals and estimates total charging energy (kWh) across fixed 60-minute time intervals. Exposes baseline forecasts and computes derived operational demand envelopes.
- **EVCharge-Opt (Optimizer):** Ingests prediction forecasts, assigns chargers/slots based on grid constraints and vehicle priorities, and feeds back operational allocation results.
- **Data Boundary:** Each application maintains independent storage. EVCharge-Predict stores historical session data, forecasts, and feedback records in its own database and never accesses the EVCharge-Opt database directly.

## 2. Shared Integration Conventions

| Parameter | Specification | Details |
| :--- | :--- | :--- |
| **Contract Version** | `1.0` | Header `X-Contract-Version: 1.0` and path `/api/v1` |
| **Shared Station IDs** | `ST-001`, `ST-002`, `ST-003`, ... | Alphanumeric canonical station identifiers |
| **Timestamp Format** | UTC ISO 8601 with `Z` suffix | Example: `2026-10-25T14:00:00Z` |
| **Forecast Interval** | 60 minutes (`3600` seconds) | Fixed hourly rolling slots |
| **Forecast Horizon** | 6 intervals (6 hours total) | Fixed 6 time bins per forecast generation |
| **Authentication** | Bearer Token | Header: `Authorization: Bearer <API_AUTH_TOKEN>` |
| **Request Correlation** | Header: `X-Request-ID` | Reflected in response header and structured logs |
| **Local Predictor URL** | `http://127.0.0.1:8001` | OpenAPI docs: `/docs` (when `ENABLE_DOCS=True`) |
| **Local Optimizer URL** | `http://127.0.0.1:8000` | Designated port for partner service |
| **Local Frontend URL** | `http://127.0.0.1:5173` | Vite development server |

---

## 3. Security & Service-to-Service Authentication

1. **Bearer Token Enforcement:**
   - Protected endpoints require an `Authorization: Bearer <token>` header matching the server's configured `API_AUTH_TOKEN`.
   - Missing Authorization header returns **`HTTP 401 Unauthorized`** (`WWW-Authenticate: Bearer`).
   - Invalid token returns **`HTTP 403 Forbidden`**.
   - **Fail-Closed in Production:** If `APP_ENV=production`, the application refuses to start if `API_AUTH_TOKEN` is missing or default.
2. **Public Operational Probe Exemptions:**
   - `GET /healthz` and `GET /api/v1/healthz` (liveness probe).
   - `GET /readyz` and `GET /api/v1/readyz` (readiness probe).
   *Rationale:* Platforms (Docker, Kubernetes, Render) require probing health without bearing rotating secret tokens.
3. **Observability & Request Tracing:**
   - Callers should pass `X-Request-ID` (or `X-Correlation-ID`) containing 8–64 alphanumeric characters, hyphens, or underscores.
   - Non-conforming or multiline values are sanitized and replaced with a fresh UUID to prevent log injection.
   - The response always returns `X-Request-ID`.

---

## 4. Core API Endpoints

### 4.1. Health & Readiness (Public)
- **`GET /healthz`** (Minimal operational liveness: `{"service":"evcharge-predict","api_version":"1.0","status":"ok"}`).
- **`GET /readyz`** (Database connectivity and model loading check without executing full model inference).

### 4.2. Baseline Forecast Workflow (Protected)
- **`POST /api/v1/forecasts`**: Generates a 6-hour recursive forecast for specified canonical stations. Returns `HTTP 201 Created` with `forecast_id`.
- **`GET /api/v1/forecasts/{forecast_id}`**: Retrieves full 6-hour predictions (`predicted_arrivals`, `predicted_energy_kwh`) per station.
- **`GET /api/v1/forecasts/latest?scenario_id=...`**: Retrieves newest completed baseline forecast for scenario.

### 4.3. Partner Feedback Ingestion & Operational Demand (Protected)
- **`POST /api/v1/feedback`**: Ingests allocation results (`allocated_energy_kwh`, `available_capacity_kw`, `reported_unmet_demand_kwh`).
  - **Deterministic Idempotency:** Uses `allocation_run_id` and SHA-256 payload hash (`201 Created` for new, `200 OK` with `is_duplicate: true` for identical repeat, `409 Conflict` for modified payload with reused run ID).
- **`GET /api/v1/feedback/{feedback_id}`**: Retrieves stored feedback metadata.
- **`GET /api/v1/feedback?forecast_id=...&scenario_id=...`**: Lists feedback submissions.
- **`GET /api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id=...`**: Retrieves station-level operational demand envelope (`v1-heuristic-operational-envelope`) comparing baseline predictions against allocated energy.

---

## 5. Contract Payload Examples
- `examples/forecast_request.json`
- `examples/forecast_create_response.json`
- `examples/forecast_response.json`
- `examples/feedback_request.json`
- `examples/feedback_create_response.json`
- `examples/adjusted_demand_response.json`
- `examples/feedback_conflict_error.json`
