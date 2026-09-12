# 二十三轮隔离测试证据

## 命令

```bash
cd backend
DATA_DIR=/tmp/ot-data-source-wiring-round23 \
.venv/bin/python -m pytest -q --tb=line
```

环境：`uv sync --extra dev` 生成的 `backend/.venv`（无仓库内预装 venv）。
无 `--network`。无 `.env`。未读取本机 `DATA_DIR`。

## 结果

```
766 passed, 42 warnings in 32.09s
```

警告与前几轮相同：Polars `streaming` 弃用、`join_asof` 未保证 sortedness、`ext_factors` 转义。无失败。

## 覆盖

- 二十三轮新用例（DuckDB 初始化、regime / 主线历史、池快照、财务 PIT 迁移、catalog token）
- 二十二轮及更早路由回归
- `data_catalog` 热路径（SQLite-only，<200ms）
- `test_regime_builder` / `test_market_mainline` / `test_reference_derived` / `test_financial_pit_e6`
