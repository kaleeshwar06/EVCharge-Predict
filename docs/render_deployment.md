# Render Deployment Guide — EVCharge-Predict

> **Important:** The EVCharge-Predict model is trained on 14-day **synthetic fixture data**, not real ACN-Data. All forecasts are illustrative and must not be used for production energy management decisions without retraining on validated real-world data.

---

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| Render account | [render.com](https://render.com) free tier is sufficient for initial deployment |
| GitHub repo | `https://github.com/kaleeshwar06/EVCharge-Predict` connected to Render |
| Python version | **3.12** (pinned via `.python-version`) |

---

## 2. Environment Variables (Render Dashboard)

Set these in **Render → Service → Environment**. Never commit secret values to Git.

| Variable | Required | Value / Source |
|---|---|---|
| `APP_ENV` | ✅ | `production` (auto-set by `render.yaml`) |
| `API_AUTH_TOKEN` | ✅ | Generate a strong random secret (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | ✅ | Auto-injected from the linked PostgreSQL database (`render.yaml` `fromDatabase`) |
| `ENABLE_DOCS` | ✅ | `false` in production (auto-set by `render.yaml`) |
| `FRONTEND_ORIGIN` | Optional | Your frontend URL (e.g. `https://your-app.onrender.com`) |

> **Security:** If `API_AUTH_TOKEN` is absent or set to the placeholder value, the service **will refuse to start** in production. This is intentional (fail-closed).

---

## 3. Build & Start Commands

These are declared in `render.yaml` and do not need to be set manually:

```
Build:  pip install -r backend/requirements.txt
Start:  uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

- `--app-dir backend` sets the Python import root to `backend/` so `app.main` resolves correctly.
- `$PORT` is injected by Render at runtime — do **not** hardcode a port.
- `0.0.0.0` is required so Render's reverse proxy can reach the service.

---

## 4. Database Migrations

Run migrations **once after the first deploy** (or after any schema change) using a Render shell:

```bash
# In Render Shell (Service → Shell tab):
cd backend
python -m alembic upgrade head
```

> **Warning:** Never run migrations against the production database without a verified backup. Alembic migrations are applied incrementally; running `upgrade head` on an already-migrated database is safe but inspect the migration chain first.

> **Warning:** Do NOT seed synthetic sessions into the production database automatically. Seeding is an explicit, manual opt-in step for development/demo only.

---

## 5. Health Check

Render uses `GET /healthz` to determine service health. The endpoint:
- Is **public** (no authentication required).
- Returns `{"status": "ok"}` when the service is ready.
- Returns a non-2xx response or times out when the service is unhealthy.

`render.yaml` sets `healthCheckPath: /healthz` automatically.

---

## 6. Model Artifacts

Model artifacts (`artifacts/models/`) are committed to Git and loaded at startup. They are trained on synthetic data.

- **Arrival model:** `artifacts/models/arrival_model.joblib`
- **Energy model:** `artifacts/models/energy_model.joblib`
- **Station encoder & metrics:** `artifacts/models/manifest.json` (contains `station_encoder` dictionary, feature definitions, and version metadata)

If artifacts are missing at startup, the forecast service will fail on first use. Verify the `artifacts/` directory is tracked in `.gitignore` correctly (it is — the models are included, raw data is excluded).

---

## 7. Post-Deployment Verification

After the first deploy, verify the following:

```bash
# 1. Health check (public)
curl https://your-app.onrender.com/healthz

# 2. Readiness probe (public)
curl https://your-app.onrender.com/readyz

# 3. Protected endpoint — expect 401 without token
curl https://your-app.onrender.com/api/v1/forecasts

# 4. Protected endpoint — expect 201 with valid token and hourly aligned UTC timestamp
curl -X POST https://your-app.onrender.com/api/v1/forecasts \
     -H "Authorization: Bearer YOUR_API_AUTH_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "scenario_id": "scenario_prod_verify_001",
       "station_ids": ["ST-001", "ST-002", "ST-003"],
       "forecast_start": "2026-10-25T10:00:00Z",
       "interval_minutes": 60,
       "horizon_intervals": 6
     }'
```

---

## 8. Rollback

If a deployment fails:
1. Use Render's **Manual Deploy → previous commit** to roll back the service.
2. If a migration was applied, revert it with `alembic downgrade -1` in the Render shell **before** rolling back the service image.
3. Do **not** unset `API_AUTH_TOKEN` as a rollback strategy — that would expose the service unauthenticated.

---

## 9. Known Limitations

| Item | Detail |
|---|---|
| Synthetic data | Model trained on 14-day synthetic fixture; not real ACN-Data |
| Stations | Only ST-001, ST-002, ST-003 are validated. ST-004/ST-005 require ingestion + retraining |
| Free tier | Render free PostgreSQL databases are deleted after 90 days; upgrade plan for persistence |
| Python version | Render target is 3.12; local development runs on 3.14 — report any incompatibilities |
