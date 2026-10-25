# EVCharge-Predict — Phase 3 Machine Learning Architecture

## 1. Overview
Phase 3 establishes an end-to-end, reproducible machine-learning training and evaluation pipeline for station-level hourly EV charging demand forecasting.

## 2. Prediction Target Definitions
- **Target A (`arrivals`):** Count of charging sessions whose connection time falls within the half-open hourly interval:
  $$\text{interval\_start} \le \text{connection\_time} < \text{interval\_end}$$
  Counted strictly by start time (disconnect time is never used to assign arrival intervals).
- **Target B (`session_start_energy_kwh`):** Total energy delivered (in kWh) for all sessions whose connection time falls within the interval:
  $$\text{session\_start\_energy\_kwh} = \sum_{\text{sessions in interval}} \text{kwh\_delivered}$$
  Only non-null, valid energy readings are summed. If energy measurements are missing for a substantial portion of the dataset (<50% coverage threshold), energy model training is skipped to avoid training on distorted zeroes.

## 3. Hourly Aggregation & Observation Span
- Every station's timeline is converted into continuous 60-minute time intervals across its observed start-to-end lifespan.
- Unobserved intermediate intervals are filled with 0 arrivals and 0.0 kWh session-start energy.
- Intervals outside a station's lifetime are not assumed to be zero.

## 4. Past-Only Feature Engineering (No Data Leakage)
Features are computed per station using strictly past observations:
- **Calendar:** Hour of day (0–23), day of week (0–6), weekend indicator (0 or 1).
- **Cyclical:** Sine and cosine encodings of hour and day of week:
  $$\sin\left(\frac{2\pi \cdot \text{hour}}{24}\right),\; \cos\left(\frac{2\pi \cdot \text{hour}}{24}\right),\; \sin\left(\frac{2\pi \cdot \text{dayofweek}}{7}\right),\; \cos\left(\frac{2\pi \cdot \text{dayofweek}}{7}\right)$$
- **Autoregressive Lags:** Lagged arrivals and lagged energy at 1, 2, 3, 6, 12, 24, 48, and 168 hours.
- **Rolling Means:** Rolling averages over 6, 24, and 168 hours computed using `shift(1)`, guaranteeing that interval $t$'s own arrival/energy is never included.
- **Station Code:** Reproducible categorical integer mapping derived from canonical IDs (`ST-001`, `ST-002`, ...).

## 5. Chronological Train / Validation / Test Splitting
- Split strictly across temporal boundaries:
  - **Train:** Earliest 70% of chronological intervals
  - **Validation:** Next 15% of chronological intervals
  - **Test:** Final 15% of chronological intervals
- No random row shuffling. Future observations never enter training or preprocessing transforms.

## 6. Models & Benchmarking
- **Historical Average Baseline:** Predicts the historical mean for `(station_id, dayofweek, hour)` computed strictly from training rows. Falls back to station mean, then global training mean if unobserved.
- **Random Forest Regressor:** `scikit-learn` `RandomForestRegressor(n_estimators=100, max_depth=12, min_samples_split=5, random_state=42)` with nonnegative output clamping (`np.clip(a_min=0.0)`).
- **Evaluation Metrics:** Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE) evaluated on identical test windows.

## 7. Artifacts & Manifest
Saved atomically under `artifacts/models/`:
- `arrival_model.joblib`: Trained arrival regressor.
- `energy_model.joblib`: Trained energy regressor.
- `manifest.json`: JSON metadata tracking timestamps, dataset fingerprints, feature names, hyperparameter configurations, test metrics, and data caveats.
- `evaluation_report.md`: Markdown report detailing overall and per-station metrics.

> **Caution:** Metrics generated from synthetic test fixtures do not establish real-world predictive accuracy. Real-world evaluation requires authentic ACN-Data sessions.
