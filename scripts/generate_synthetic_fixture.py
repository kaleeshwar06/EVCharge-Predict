"""Generates a multi-day deterministic synthetic dataset for model pipeline tests."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random

random.seed(42)
start_date = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
stations = ["1-39-139-650", "1-39-139-651", "1-39-139-652"]
items = []

sess_counter = 1
# Generate 14 days (336 hours) of sessions
for day in range(14):
    for hr in range(24):
        cur_time = start_date + timedelta(days=day, hours=hr)
        # Peak arrivals in morning (8-11) and evening (17-20)
        is_peak = hr in (8, 9, 10, 11, 17, 18, 19, 20)
        n_sessions = random.randint(1, 3) if is_peak else (1 if random.random() < 0.3 else 0)

        for _ in range(n_sessions):
            st = random.choice(stations)
            minute = random.randint(0, 59)
            conn_time = cur_time + timedelta(minutes=minute)
            duration_hrs = random.uniform(1.0, 4.0)
            disc_time = conn_time + timedelta(hours=duration_hrs)
            kwh = round(duration_hrs * random.uniform(6.0, 11.0), 2)

            items.append({
                "sessionID": f"synth-sess-{sess_counter:04d}",
                "stationID": st,
                "siteID": "caltech",
                "connectionTime": conn_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "disconnectTime": disc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kWhDelivered": kwh,
                "timezone": "America/Los_Angeles"
            })
            sess_counter += 1

fixture_path = Path("backend/tests/fixtures/synthetic_14day_sessions.json")
with open(fixture_path, "w", encoding="utf-8") as f:
    json.dump({"_meta": {"site": "caltech", "type": "synthetic"}, "_items": items}, f, indent=2)

print(f"Generated {len(items)} synthetic sessions over 14 days at {fixture_path}")
