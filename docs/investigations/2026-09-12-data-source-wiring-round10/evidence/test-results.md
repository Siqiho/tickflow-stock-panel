# Isolated pytest (no network)

Command (from `backend/`, isolated `DATA_DIR`):

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round10 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_ten_route_hardening.py \
    tests/test_round_nine_route_hardening.py \
    ...
```

Result: pending isolated run on this branch.
