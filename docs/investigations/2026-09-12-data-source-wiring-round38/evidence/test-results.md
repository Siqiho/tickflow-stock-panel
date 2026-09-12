# 三十八轮隔离测试证据

环境：云 agent，隔离 `DATA_DIR`，不读 `.env`，不写正式数据。测试结果在实现提交后补记。

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round38 \
  .venv/bin/python -B -m pytest -q --tb=line \
    tests/test_round_thirty_eight_route_hardening.py \
    tests/test_round_thirty_seven_route_hardening.py \
    tests/test_leftover_route_hardening.py
```
