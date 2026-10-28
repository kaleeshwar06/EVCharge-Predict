# EVCharge-Predict â†” EVCharge-Opt Live Integration Readiness Report

**Report Date:** October 26, 2026
**Repository:** `kaleeshwar06/EVCharge-Predict` â€” branch `main`
**Current HEAD:** `f4dd6e0c6d0c56cec8384004cec2f2cbff148783` (`docs: add EVCharge-Opt integration contract`)
**Predictor Service:** `https://evcharge-predict.onrender.com`
**EVCharge-Opt Frontend:** `https://evcharge-opt.onrender.com`
**EVCharge-Opt Backend:** `https://evcharge-opt-api.onrender.com`
**Partner Status:** EVCharge-Opt operating in mock mode pending live verification.

> [!IMPORTANT]
> This document is a **read-only verification report**. No application code changes, database migrations, data imports, production POST requests, deployments, commits, or pushes were performed during its preparation. All evidence is derived from source code inspection (`backend/app/`) and automated test execution.

---

## Evidence Tiers

Throughout this document all conclusions are tagged with one of four evidence tiers:

| Tag | Meaning |
| :--- | :--- |
| ðŸŸ¢ **Code-verified** | Confirmed by direct source-code inspection (file + line reference). |
| ðŸŸ¢ **Test-verified** | Confirmed by passing automated tests (test file + test name). |
| ðŸŸ¡ **Previously verified** | Confirmed against the deployed service in an earlier session; not re-confirmed in this session. |
| ðŸ”´ **Not yet verified** | No end-to-end confirmation; awaiting preconditions or partner action. |

---

## Task 1 â€” Feedback Interval Requirements

### Q1. Does `POST /api/v1/feedback` require ALL six intervals for every station?

**Answer: No. Partial interval sets are accepted by both schema and service.**

Evidence:

- **Schema** (`backend/app/schemas/feedback.py:37`) â€” `StationAllocationFeedbackInput.intervals` is declared with `min_length=1`. There is **no `max_length` constraint** and no validator that checks the submitted count equals the forecast horizon. ðŸŸ¢ **Code-verified**

- **Service** (`backend/app/services/feedback_service.py:147â€“156`) â€” The alignment check iterates only over the intervals *submitted*; it verifies each submitted interval maps to a forecast interval, but it never checks whether *all* forecast intervals are covered. ðŸŸ¢ **Code-verified**

  ```python
  # feedback_service.py:147â€“156 (exact source)
  for st_input in request.stations:
      st_pk = stations_map[st_input.station_id].id
      for int_in in st_input.intervals:
          key = (st_pk, int_in.interval_start)
          if key not in baseline_intervals:
              raise FeedbackIntervalAlignmentError(...)
  ```

- **Automated tests** confirm partial submission is accepted â€” the idempotency test (`test_feedback_idempotent_retry_and_conflict_detection`) submits only **1 interval** for a station whose forecast has **6 intervals** and receives `HTTP 201`. ðŸŸ¢ **Test-verified** (`backend/tests/test_feedback.py:182â€“198`)

- The baseline immutability test (`test_baseline_forecast_strictly_immutable_after_feedback`) also submits 1 of 6 intervals and expects HTTP 201. ðŸŸ¢ **Test-verified** (`backend/tests/test_feedback.py:251â€“266`)

### Q2. Which HTTP status codes apply to interval-related rejections?

| Condition | Status Code | Exception | Evidence |
| :--- | :--- | :--- | :--- |
| Submitted interval not in forecast | `HTTP 400` | `FeedbackIntervalAlignmentError` | `backend/app/api/v1/routes/feedback.py`; `test_feedback_validation_rejections` test case 4 ðŸŸ¢ Test-verified |
| Duplicate `interval_start` within same station in same request | `HTTP 422` | Pydantic `ValueError` from `validate_intervals_unique_ordered` | `backend/app/schemas/feedback.py:47â€“55` ðŸŸ¢ Code-verified |
| `interval_end <= interval_start` | `HTTP 422` | Pydantic `ValueError` from `validate_interval_bounds` | `backend/app/schemas/feedback.py:27â€“31` ðŸŸ¢ Code-verified |

### Q3. Summary for EVCharge-Opt Partner

EVCharge-Opt **may submit any subset of the 6 forecast intervals** (minimum 1 per station). Every submitted interval must:
1. Match the exact `interval_start` UTC timestamp of a corresponding forecast interval for that station.
2. Not be duplicated within the same station within a single request.
3. Have `interval_end > interval_start`.

Any unsubmitted intervals will simply have no adjusted demand record computed.

---

## Task 2 â€” HTTP 201 Feedback Response Schema

### Model: `FeedbackCreateResponse`

Source: `backend/app/schemas/feedback.py:88â€“104` ðŸŸ¢ **Code-verified**

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `contract_version` | `string` | Always present (default `"1.0"`) | Integration contract version |
| `feedback_id` | `string` | Yes | Assigned ID, format `fbk_<12 hex chars>` |
| `allocation_run_id` | `string` | Yes | Echo of submitted `allocation_run_id` |
| `forecast_id` | `string` | Yes | Echo of submitted `forecast_id` |
| `scenario_id` | `string` | Yes | Echo of submitted `scenario_id` |
| `status` | `string` | Yes | `"accepted"` on initial submission |
| `is_duplicate` | `boolean` | Yes | `false` on 201, `true` on 200 retry |
| `received_at` | `string` | Yes | UTC ISO 8601, format `YYYY-MM-DDTHH:MM:SSZ` |
| `feedback_url` | `string` | Yes | Relative path: `/api/v1/feedback/<feedback_id>` |

### HTTP Status Code Behavior

| Status Code | When | `is_duplicate` |
| :--- | :--- | :--- |
| `HTTP 201 Created` | New, unique `allocation_run_id` | `false` |
| `HTTP 200 OK` | `allocation_run_id` exists, payload SHA-256 identical | `true` |
| `HTTP 409 Conflict` | `allocation_run_id` exists, payload content differs | N/A (error body) |

> **Note:** The `HTTP 409` response body is `{"detail": "Allocation run '...' was already submitted with different content."}`. Verified at `backend/app/api/v1/routes/feedback.py` ðŸŸ¢ **Code-verified**.

> **OpenAPI schema:** `POST /api/v1/feedback` documents all three response codes. `HTTP 201` and `HTTP 200` both reference `FeedbackCreateResponse` (with `is_duplicate: false` and `is_duplicate: true` respectively). `HTTP 409` documents a `{"detail": string}` error body. Verified in `integration-contract/openapi_schema.json` and by automated tests `test_openapi_feedback_post_documents_201_200_409` and `test_openapi_feedback_post_201_and_200_reference_feedback_create_response_schema`. ðŸŸ¢ **Test-verified**

### Test Evidence

`test_feedback_api_full_http_lifecycle` (`backend/tests/test_feedback.py:367â€“465`):
- Initial POST â†’ `HTTP 201`, `is_duplicate=false`, `status="accepted"` ðŸŸ¢ **Test-verified**
- Identical retry â†’ `HTTP 200`, `is_duplicate=true`, same `feedback_id` ðŸŸ¢ **Test-verified**
- `test_feedback_idempotent_retry_and_conflict_detection` â†’ `FeedbackConflictError` raised ðŸŸ¢ **Test-verified**

---

## Task 3 â€” Historical Data Readiness Pre-flight Check

### Forecasting Prerequisite

- **Window:** `[forecast_start âˆ’ 21 days, forecast_start)` (exclusive upper bound) ðŸŸ¢ **Code-verified**
- **Threshold:** >= 5 session observations per station within that window ðŸŸ¢ **Code-verified**
- **Failure response:** `HTTP 400 Bad Request` (`InsufficientHistoryError`)

### Sessions Endpoint Contract

`GET /api/v1/sessions` â€” Source: `backend/app/api/v1/routes/sessions.py` ðŸŸ¢ **Code-verified**

| Parameter | Type | Default | Constraint | Description |
| :--- | :--- | :--- | :--- | :--- |
| `station_id` | `string` | `null` | Optional | Canonical station ID, e.g., `ST-001` |
| `start_time` | `datetime` | `null` | Optional | UTC ISO 8601; filters `connection_time >= start_time` |
| `end_time` | `datetime` | `null` | Optional | UTC ISO 8601; filters `connection_time <= end_time` |
| `limit` | `integer` | `50` | 1â€“500 | Maximum records returned |
| `offset` | `integer` | `0` | >= 0 | Pagination offset |

Response: `HTTP 200` + `List[ChargingSessionRead]` array (may be empty).

`ChargingSessionRead` fields (`backend/app/schemas/charging_session.py:41â€“59` ðŸŸ¢ **Code-verified**):

| Field | Type | Required |
| :--- | :--- | :--- |
| `id` | `integer` | Yes |
| `source_session_id` | `string` or `null` | Optional |
| `station_id` | `string` | Yes (canonical) |
| `connection_time` | `string` (UTC ISO 8601) | Yes |
| `disconnect_time` | `string` or `null` | Optional |
| `kwh_delivered` | `number` or `null` | Optional |
| `source_site_id` | `string` or `null` | Optional |
| `source_timezone` | `string` or `null` | Optional |
| `source_dataset` | `string` | Yes |

**Pre-flight query template** (check >= 5 sessions in 21-day window before `forecast_start`):

```
GET /api/v1/sessions?station_id=ST-001&start_time=<forecast_start-21d>&end_time=<forecast_start>&limit=5
Authorization: Bearer <API_AUTH_TOKEN>
```

If fewer than 5 records return â†’ history is insufficient â†’ `POST /api/v1/forecasts` will return `HTTP 400`.

> **Authentication required:** `GET /api/v1/sessions` is protected by `Depends(verify_service_token)` applied globally at `backend/app/api/v1/router.py:13â€“18`. ðŸŸ¢ **Code-verified**

### Current Production Session Data Status

ðŸ”´ **Not yet verified** â€” `alembic upgrade head` has not been run on the production Render database. No session records are known to exist.

---

## Task 4 â€” Station Inventory Verification Checklist

All entries exist in `data/processed/station_mapping.json`. Evidence is **software-only** â€” no physical hardware commissioning documents are present in this repository.

### ST-001

| Check | Status | Evidence Tier |
| :--- | :--- | :--- |
| Canonical ID present in `station_mapping.json` | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Source station ID `1-39-139-650` mapped | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Used in automated forecast and feedback fixtures | âœ… Confirmed | ðŸŸ¢ Test-verified |
| Physical hardware identity independently confirmed | âŒ Not confirmed | No commissioning document in repo |
| Live charging sessions in production DB | ðŸ”´ Not yet verified | Requires migration + data import |

### ST-002

| Check | Status | Evidence Tier |
| :--- | :--- | :--- |
| Canonical ID present in `station_mapping.json` | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Source station ID `1-39-139-651` mapped | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Used in automated feedback fixtures | âœ… Confirmed | ðŸŸ¢ Test-verified |
| Physical hardware identity independently confirmed | âŒ Not confirmed | No commissioning document in repo |
| Live charging sessions in production DB | ðŸ”´ Not yet verified | Requires migration + data import |

### ST-003

| Check | Status | Evidence Tier |
| :--- | :--- | :--- |
| Canonical ID present in `station_mapping.json` | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Source station ID `1-39-139-652` mapped | âœ… Confirmed | ðŸŸ¢ Code-verified |
| Used in any automated test or fixture | âŒ Not present | No test references ST-003 |
| Physical hardware identity independently confirmed | âŒ Not confirmed | No commissioning document in repo |
| Safe to ingest genuine sessions | âŒ **BLOCKED** | Hardware identity must be confirmed first |

> **CAUTION: ST-003 is provisional. Genuine charging session data must NOT be ingested until the hardware identity is independently confirmed by the site operator (serial number, nameplate, or utility interconnection log).**

---

## Task 5 â€” Joint Test Sequence

### Prerequisites (EVCharge-Predict operator action required)

| # | Prerequisite | Status |
| :--- | :--- | :--- |
| P1 | Run `alembic upgrade head` on production Render database | ðŸ”´ Not done â€” awaiting approval |
| P2 | Import >= 5 historical sessions per station (ST-001 and ST-002 only) | ðŸ”´ Not done â€” blocked on P1 |
| P3 | Share `API_AUTH_TOKEN` with EVCharge-Opt team via out-of-band secure channel | ðŸ”´ Not confirmed |
| P4 | Set `FRONTEND_ORIGIN=https://evcharge-opt.onrender.com` in Render environment | ðŸ”´ Not confirmed |

### Step 1 â€” Health and Readiness Probes (Public, Auth-Exempt)

```
GET https://evcharge-predict.onrender.com/healthz
GET https://evcharge-predict.onrender.com/readyz
```

**Success criteria:** Both return `HTTP 200`. `/readyz` body includes `"database": "ok"` and `"models": "loaded"`.
**Stop condition:** If `/readyz` returns `503` â†’ ML models unloaded or DB unreachable â€” do not proceed.
**Evidence tier:** ðŸŸ¡ **Previously verified** (not re-confirmed in this session)

---

### Step 2 â€” Authentication Verification

```
GET https://evcharge-predict.onrender.com/api/v1/stations  [wrong token]
```
Expected: `HTTP 403`

```
GET https://evcharge-predict.onrender.com/api/v1/stations  [correct token]
```
Expected: `HTTP 200` + JSON array.

**Evidence tier:** ðŸŸ¢ **Test-verified** (`test_service_to_service_auth_enforcement_and_public_probes`)

---

### Step 3 â€” Session Pre-flight Check (ST-001)

```
GET /api/v1/sessions?station_id=ST-001&start_time=<T-21d>&end_time=<T>&limit=5
Authorization: Bearer <token>
```

**Success criteria:** Response array contains >= 5 objects.
**Stop condition:** Fewer than 5 â†’ P2 incomplete â†’ do not proceed to forecasting.
**Evidence tier:** ðŸ”´ **Not yet verified end to end**

---

### Step 4 â€” Baseline Forecast Generation

```json
POST /api/v1/forecasts
{
  "scenario_id": "live_test_01",
  "station_ids": ["ST-001"],
  "forecast_start": "<next exact UTC hour>",
  "interval_minutes": 60,
  "horizon_intervals": 6
}
```

**Success criteria:** `HTTP 201`, response contains `forecast_id` (`fcst_` prefix), `status: "completed"`, `demand_type: "baseline"`.
**Stop conditions:**
- `HTTP 400` (`InsufficientHistoryError`) â†’ Step 3 failed
- `HTTP 422` â†’ `forecast_start` not aligned to exact UTC hour
- `HTTP 503` â†’ models not loaded

**Evidence tier:** ðŸ”´ **Not yet verified end to end**

---

### Step 5 â€” Forecast Retrieval

```
GET /api/v1/forecasts/<forecast_id>
```

**Success criteria:** `HTTP 200`, 6 intervals with `predicted_arrivals` (int >= 0) and `predicted_energy_kwh` (float >= 0.0).
**Evidence tier:** ðŸ”´ **Not yet verified end to end**

---

### Step 6 â€” Feedback Submission (Partial Intervals Accepted)

```json
POST /api/v1/feedback
{
  "contract_version": "1.0",
  "allocation_run_id": "live_test_run_001",
  "forecast_id": "<forecast_id from Step 4>",
  "scenario_id": "live_test_01",
  "submitted_at": "<current UTC ISO 8601>",
  "optimizer_version": "evcharge-opt-mock-v1",
  "stations": [{
    "station_id": "ST-001",
    "intervals": [{
      "interval_start": "<exact interval_start from Step 5 response>",
      "interval_end": "<exact interval_end from Step 5 response>",
      "allocated_energy_kwh": 30.0,
      "available_capacity_kw": 50.0,
      "reported_unmet_demand_kwh": 0.0
    }]
  }]
}
```

**Key verified contract points:**
- `interval_start` must exactly match forecast interval timestamp (UTC, timezone-aware). ðŸŸ¢ Code-verified
- Partial submission (1 of 6 intervals) is accepted. ðŸŸ¢ Code-verified + ðŸŸ¢ Test-verified
- `allocated_energy_kwh`, `available_capacity_kw`, `reported_unmet_demand_kwh` are all optional (may be null). ðŸŸ¢ Code-verified

**Success criteria:** `HTTP 201`, `feedback_id` (`fbk_` prefix), `is_duplicate: false`, `status: "accepted"`.
**Idempotency test:** Re-send identical payload â†’ expected `HTTP 200`, `is_duplicate: true`, same `feedback_id`. ðŸŸ¢ Test-verified
**Evidence tier:** ðŸ”´ **Not yet verified end to end**

---

### Step 7 â€” Feedback Metadata Retrieval

```
GET /api/v1/feedback/<feedback_id>
```

**Success criteria:** `HTTP 200`, body contains `feedback_id`, `allocation_run_id`, `forecast_id`, `scenario_id`, `status`, `submitted_at`, `received_at`.
**Evidence tier:** ðŸ”´ **Not yet verified end to end**

---

### Step 8 â€” Adjusted Demand Retrieval

```
GET /api/v1/forecasts/<forecast_id>/adjusted-demand?feedback_id=<feedback_id>
```

**Success criteria:**
- `HTTP 200`
- `demand_type: "feedback-adjusted-operational"`
- `adjustment_policy_version: "v1-heuristic-operational-envelope"`
- Each submitted interval: `adjusted_operational_demand_kwh = max(baseline_energy_kwh, allocated_energy_kwh)`
- Intervals NOT submitted in feedback: absent from adjusted demand response
- Baseline values (`baseline_arrivals`, `baseline_energy_kwh`) identical to Step 5 values

**Evidence tier:** ðŸ”´ **Not yet verified end to end** (policy calculation ðŸŸ¢ Test-verified)

---

## Summary â€” Current Readiness Status

| Domain | Ready? | Blocking Issue |
| :--- | :--- | :--- |
| API contract documented | âœ… Yes | â€” |
| Schema and code verified | âœ… Yes | â€” |
| Automated tests (8/8 feedback + 72/72 full suite) | âœ… Yes | â€” |
| Deployment health probes | ðŸŸ¡ Previously verified | Not re-confirmed in this session |
| Production database migrations | âŒ No | `alembic upgrade head` not run |
| Historical session data per station | âŒ No | Requires migration first |
| Authentication token shared with partner | âŒ Unknown | Out-of-band confirmation required |
| CORS `FRONTEND_ORIGIN` confirmed | âŒ Unknown | Render env var not confirmed |
| Live forecasting workflow (end to end) | âŒ Not verified | Requires P1â€“P4 |
| Live feedback workflow (end to end) | âŒ Not verified | Requires P1â€“P4 |
| ST-003 hardware identity | âŒ Not confirmed | Site operator confirmation required |

> [!IMPORTANT]
> **Mock mode must remain enabled until the complete live end-to-end workflow passes.**
> Completing prerequisites P1â€“P4 and passing the initial probes (Steps 1â€“3) confirms infrastructure readiness only. EVCharge-Opt must keep mock mode active until Steps 4â€“8 (live forecast generation, forecast retrieval, feedback submission including idempotent retry verification, feedback metadata retrieval, and adjusted demand retrieval) have all been executed successfully with actual production data and explicitly approved by both parties.

---

*Report prepared from read-only code and automated test inspection. No application code, configuration, environment variables, or production data were modified.*
