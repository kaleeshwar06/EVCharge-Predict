# EVCharge-Predict — Model Training & Evaluation Report

- **Generated At (UTC):** 2026-10-24T21:41:03Z
- **Dataset Source:** file:synthetic_14day_sessions.json
- **Data Type:** SYNTHETIC FIXTURE
- **Total Raw Records:** 309
- **Valid Sessions:** 309
- **Stations:** 3 (ST-001, ST-002, ST-003)
- **Energy Coverage Ratio:** 100.0%
- **Time Span:** 331.7 hours

## Chronological Split Boundaries
- **Train:** 2026-10-01T02:00:00Z to 2026-10-10T16:00:00Z
- **Validation:** 2026-10-10T17:00:00Z to 2026-10-12T18:00:00Z
- **Test:** 2026-10-12T19:00:00Z to 2026-10-14T20:00:00Z

## Model Performance Summary

| Target | Baseline Test MAE | Baseline Test RMSE | RF Test MAE | RF Test RMSE | RF Outperformed? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| arrivals (sessions/hour) | 0.336 | 0.685 | 0.403 | 0.557 | NO |
| session_start_energy_kwh (kWh) | 7.049 | 13.872 | 8.445 | 11.862 | NO |

## Limitations & Data Warnings
- ⚠️ Model trained on synthetic fixtures. Metrics do not establish real-world predictive accuracy.
