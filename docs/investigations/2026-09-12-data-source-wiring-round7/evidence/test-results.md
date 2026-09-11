# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round7 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_minute_availability.py \
    tests/test_capability_matrix.py \
    tests/test_data_source_write_path.py \
    tests/test_realtime_mode.py \
    tests/test_custom_depth_provider.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py
```

Result: pending isolated run in this environment.

No `.env` read. No live network. Formal `DATA_DIR` / user Mac tree not touched.
