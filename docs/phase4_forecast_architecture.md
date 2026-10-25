# EVCharge-Predict — Phase 4: Forecast Engine & API Architecture

## 1. Overview
Phase 4 implements the production-minded forecasting service exposing the agreed versioned REST API contract for **EVCharge-Opt**.

## 2. Model Loading & Verification
- **Artifact Directory:** Default `artifacts/models/` (configurable via `MODEL_ARTIFACT_DIR`).
- **Singleton Model Service:** `ModelService.get_instance()` loads artifacts once per worker process.
- **Verification on Startup / Request:**
  - Verifies presence and JSON structure of `manifest.json`.
  - Enforces `scikit-learn` version compatibility between manifest and runtime environment.
  - Verifies that `arrival_model.joblib` and `energy_model.joblib` feature schemas match the 30-feature training manifest.
  - Runs an automated sanity test inference before declaring the model service loaded.
  - Non-model endpoints (`/healthz`) remain available even if models are not loaded.
  - `/readyz` returns `503 Service Unavailable` if database or models are not ready.

## 3. Recursive Autoregressive Forecasting Algorithm
To forecast $H = 6$ future consecutive hourly intervals ($t, t+1, \dots, t+5$):
1. **History Window Retrieval:** Queries database charging sessions for the requested station strictly prior to $t$ ($[t - 21\text{d}, t)$).
2. **History Construction:** Aggregates sessions into continuous hourly intervals, filling unobserved hours with $0$ arrivals and $0.0$ kWh.
3. **Step 1 ($t$):** Constructs features using actual past observations up to $t-1$. Predicts arrivals and energy for interval $t$.
4. **Step 2 to 6 ($t+1 \dots t+5$):**
   - Appends predicted arrivals and energy from previous intervals into in-memory working history.
   - Computes autoregressive lag features (`lag_1h`, `lag_2h`, ...) and rolling averages (`rolling_6h_mean`, ...) where recent history incorporates earlier predictions.
   - Advances hour and day-of-week calendar and cyclical features deterministically in UTC.
5. **Output Policy:**
   - Predicted arrivals: Non-negative and rounded to whole integer session count: `int(np.round(max(0.0, raw_arr)))`.
   - Predicted energy: Non-negative float rounded to 3 decimal places (kWh): `round(max(0.0, raw_ene), 3)`.
6. **Isolation:** Each station is computed independently in-memory; prediction errors roll back the entire transaction.

## 4. Endpoints Implemented
- `GET /healthz` & `GET /api/v1/healthz`: Liveness check.
- `GET /readyz` & `GET /api/v1/readyz`: Readiness check verifying database connectivity and loaded model state.
- `POST /api/v1/forecasts`: Generates and persists a 6-interval forecast for all requested stations.
- `GET /api/v1/forecasts/{forecast_id}`: Retrieves complete multi-station forecast by unique ID.
- `GET /api/v1/forecasts/latest?scenario_id=...`: Retrieves the latest completed baseline forecast for a scenario.

## 5. Database Schema & Persistence
- Table `forecasts`: Stores `forecast_id`, `scenario_id`, `forecast_start`, `forecast_end`, `generated_at`, `status`, `demand_type`, and model provenance.
- Table `forecast_intervals`: Stores station ID, `interval_start`, `interval_end`, `predicted_arrivals`, and `predicted_energy_kwh`.
- Alembic migration `f5f5b0b6fffb_add_forecast_and_interval_tables.py` manages schema evolution.
