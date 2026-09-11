# TEST-ONLY leftover quote samples

用途：仅本包隔离复现。不是正式行情，不含 token / 身份。

不要写入 `data/shared-isolated-runtime-20260911` 或任何 shared `DATA_DIR`。

## 将写哪些隔离文件

脚本默认只写调用方给出的 `--data-dir`（默认 `/tmp/ot-overview-scope-repro`）：

- `$DATA_DIR/quote_snapshot/asset_type=stock/date=2026-09-11/part.parquet`
- 可选打印 `build_market_overview` 的 coverage / breadth / amount

## 还原

删除该临时目录即可。不要用它覆盖正式 `data/`。

样本语义：5 只旧 quote、无 `scope` 元信息、4 涨 / 0 平 / 1 跌、成交额 55.72 亿。修前会被当成今日全市场；修后合计应为 null，并标明范围未知。
