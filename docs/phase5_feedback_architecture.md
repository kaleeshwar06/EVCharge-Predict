# Phase 5: Feedback Architecture & Adjustment Policy Specification

## 1. Overview & Architecture

EVCharge-Predict communicates with EVCharge-Opt strictly across REST boundaries over JSON. The two applications maintain complete database isolation.

```
┌─────────────────────────┐                                ┌─────────────────────────┐
│     EVCharge-Predict    │                                │      EVCharge-Opt       │
│  (Demand Forecasting)   │                                │  (Charger Optimization) │
└────────────┬────────────┘                                └────────────┬────────────┘
             │                                                          │
             │ 1. POST /api/v1/forecasts                                │
             │ ◄────────────────────────────────────────────────────────┤
             │ 2. Return 6-hr baseline forecast (predicted_energy/arr)  │
             ├─────────────────────────────────────────────────────────►│
             │                                                          │
             │                                                [ Runs optimizer ]
             │                                                [ under grid /   ]
             │                                                [ charger limits ]
             │                                                          │
             │ 3. POST /api/v1/feedback                                 │
             │    (allocation_run_id, allocated_kwh, capacity_kw)       │
             │ ◄────────────────────────────────────────────────────────┤
             │ 4. Return 201/200 (feedback_id, is_duplicate)            │
             ├─────────────────────────────────────────────────────────►│
             │                                                          │
             │ 5. GET /api/v1/forecasts/{id}/adjusted-demand            │
             │ ◄────────────────────────────────────────────────────────┤
             │ 6. Return operational demand envelope                    │
             ├─────────────────────────────────────────────────────────►│
```

---

## 2. Policy v1: Heuristic Operational Envelope

- **Policy ID:** `v1-heuristic-operational-envelope`
- **Units:**
  - `baseline_energy_kwh`: kWh
  - `allocated_energy_kwh`: kWh
  - `available_capacity_kw`: kW
  - `reported_unmet_demand_kwh`: kWh
  - `adjusted_operational_demand_kwh`: kWh
  - `baseline_arrivals`: integer count

### 2.1 Formula
For station $s$ and hourly interval $t$:
$$\text{adjusted\_operational\_demand\_kwh}_{s,t} = \max(\text{baseline\_energy\_kwh}_{s,t},\, \text{allocated\_energy\_kwh}_{s,t})$$

$$\text{adjustment\_status}_{s,t} = \begin{cases}
\text{"adjusted"}, & \text{if } \text{allocated\_energy\_kwh}_{s,t} > \text{baseline\_energy\_kwh}_{s,t} \\
\text{"unchanged"}, & \text{if } \text{allocated\_energy\_kwh}_{s,t} \le \text{baseline\_energy\_kwh}_{s,t} \\
\text{"insufficient_data"}, & \text{if } \text{allocated\_energy\_kwh}_{s,t} \text{ is omitted}
\end{cases}$$

### 2.2 Invariants & Limitations
1. **Allocated energy is NOT ground truth physical demand:** Allocated energy represents the optimizer's scheduling outcome constrained by grid capacity, transformer ratings, or cable limits. The `max` envelope represents the operational energy demand required to fulfill either model baseline or actual optimizer schedule.
2. **Arrivals are never fabricated:** `baseline_arrivals` is preserved as-is. We do not invent session counts from energy numbers.
3. **Unmet demand is strictly pass-through:** We never subtract `predicted_energy - allocated_energy` to invent an unmet demand figure. Unmet demand is reported only if explicitly provided in `reported_unmet_demand_kwh`.
4. **Baseline Forecasts are Strictly Immutable:** Baseline forecasts stored in `forecast_intervals` are never updated or overwritten. Derived results live in a completely separate table `adjusted_demand_intervals`.

---

## 3. Idempotency & Conflict Handling

- **Idempotency Key:** `allocation_run_id` (unique per optimizer run).
- **Payload Hash:** SHA-256 fingerprint over normalized JSON payload.
- **Rules:**
  - **New run:** `HTTP 201 Created` with `is_duplicate: false`.
  - **Identical retry:** `HTTP 200 OK` with existing `feedback_id` and `is_duplicate: true`.
  - **Conflicting run (modified body with same run ID):** `HTTP 409 Conflict` with clear error detail.
