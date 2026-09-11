# StockDB 隔离离线导出

as_of: 2026-09-05。主台：数据台。实现状态以[数据平台开发日志](/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#stockdb-offline-export)为准。

范围说明：下文离线步骤记录已完成的原始全量导出，不自动授权再次扫描或联网更新。2026-09-05 22:20 用户另行授权的官方 Mac 包同内容重装与原生 SDK 小样验证，见本文末节及开发日志 #stockdb-native-sdk-check。

## 目标与非目标

把已有 StockDB 镜像恢复为普通工具可读的 Parquet，保留所有有效业务 KV 的原值与来源。不安装/构建上游 Runtime，不联网更新，不写正式 `one-trading/data`，不自动增加 Provider/Catalog/API/UI。

本轮原库：`/Users/simon/Trading/下载数据/股票数据/stockdb` 的 `data`、`data1`、`mydb`。

用户授权暂停原 StockDB、固定快照、全量导出并恢复；不包含停 one-trading 或数据生产接入。

## 固定输入与恢复

1. 先检查 PID、可执行文件、cwd、配置和端口，仅暂停目标 StockDB。客户端全局 keys 超时不会可靠取消服务端扫描；禁止用这个接口做全库枚举。
2. 在 `/Users/simon/备份/codex` 新建专用备份目录并写 README。本轮快照为 `/Users/simon/备份/codex/20260905-stockdb-export-source-snapshot`，APFS COW 保留原库。不要在快照上打开任何可写 LevelDB 引擎。
3. 从 CURRENT 指定的 MANIFEST 重放增删文件记录，仅消费有效 SST 和当前/前一 WAL；不遍历全部物理旧 SST 再简单叠加。原库运行时正有压缩产生的过期文件，目录大小不等于有效业务体积。
4. 导出结束后、恢复前，校验原库与快照所有 active 文件的 SHA-256 相同；恢复查询进程，做精确 key 核验。若原请求仍未取消，恢复应清掉它，避免继续全局扫描。
5. 不把快照覆盖回原库，不清理原库旧文件，不自动删除备份或 canary。

## 实现与依赖

脚本：`scripts/stockdb_offline_export.py`、`scripts/validate_stockdb_export.py`、`scripts/profile_stockdb_export.py`、`scripts/quarantine_stockdb_export.py`、`scripts/reconcile_stockdb_overlap.py`；测试：`scripts/test_stockdb_offline_export.py`（本轮 11 项通过）。

使用已有 backend venv 的 Python 3.13.5 / PyArrow 24.0.0。三个小依赖只安装到项目 `.stockdb-export-deps`，没有改服务 venv 或全局配置：

```bash
uv pip install --python /Users/simon/Trading/one-trading/backend/.venv/bin/python \
  --target /Users/simon/Trading/one-trading/.stockdb-export-deps \
  -r /Users/simon/Trading/one-trading/scripts/stockdb-export-requirements.txt
```

只读解析依据：[LevelDB SST 格式](https://github.com/google/leveldb/blob/main/doc/table_format.md)、[日志格式](https://github.com/google/leveldb/blob/main/doc/log_format.md)、[VersionEdit](https://github.com/google/leveldb/blob/main/db/version_edit.cc)。本地实物为压缩类型 2 + Zstd magic，业务值主要 MessagePack；并不假设公开 StockDB C++ 示例与二进制相同。

支持 bytewise comparator、内部 key 的 sequence/type、标准日志 FULL/FIRST/MIDDLE/LAST、SST prefix/restart/index、CRC32C。未知 comparator/压缩/版本标签/坏 CRC/同序号冲突立即失败；不静默跳过损坏。只允许未完成最终 WAL/MANIFEST 尾片段按 LevelDB 日志语义忽略并记录，不忽略中间损坏。

## 执行与验收

```bash
/Users/simon/Trading/one-trading/backend/.venv/bin/python -B -m unittest discover \
  -s /Users/simon/Trading/one-trading/scripts -p test_stockdb_offline_export.py -v

nice -n 10 /Users/simon/Trading/one-trading/backend/.venv/bin/python -B \
  /Users/simon/Trading/one-trading/scripts/stockdb_offline_export.py export \
  /Users/simon/备份/codex/20260905-stockdb-export-source-snapshot \
  --output /Users/simon/Trading/下载数据/stockdb_parquet --workers 4

/Users/simon/Trading/one-trading/backend/.venv/bin/python -B \
  /Users/simon/Trading/one-trading/scripts/validate_stockdb_export.py \
  /Users/simon/Trading/下载数据/stockdb_parquet \
  --original /Users/simon/Trading/下载数据/股票数据/stockdb --workers 3
```

验收必须在原库仍固定时完成。仅有 `export_complete.json` 是“导出结束、待验证”；还需要 `validation.json` 和恢复后 `service_restore.json`，不得凭文件出现就声称闭环。

全量转换后依次运行 profile_stockdb_export.py、quarantine_stockdb_export.py、reconcile_stockdb_overlap.py，唯一位置参数是输出目录；它们只生成质量/扁平/异常旁路文件，不改归档原值。只对 data/data1 实际交叠时间窗口做键分组，不能对 6 亿分钟键直接内存 GROUP BY。`validate_stockdb_export.py --prevalidate` 可先校验已完成区间，最终复用前仍重算输出 hash；不会单独发布 validation.json。

全量校验：每页 Parquet 重开/页校验和、每文件 SHA-256、每条原始 key/sequence/value 的有序 SHA-256 与导出读取流一致、同库键唯一、分区不重叠、输入版本数 = 保留记录 + 旧/重复版本 + 最新删除标记；每批首/中/末记录做可读字段与原值分层抽样。市场质量另作 QC，不等于校验和正确即可用于交易。

## 目录与读取

`tables/` 分为 minute_bars、daily_bars、adjustment_factors、sector_snapshots、instrument_lists、market_mapping、delisting_records、auxiliary_records。证券/板块/退市的嵌套形态先保存为可读 JSON，后续可从它们生成扁平辅助表，不能丢失原记录。

通用字段：source_db、source_file、source_sequence、physical_key、logical_key、payload_encoding、payload_raw。payload_raw 是原始业务值，不是重新编码的近似值；MessagePack 可用 msgpack.unpackb 解码，其余按 payload_encoding 读取。未知字段保存在 extra_json / payload_json，完整原字节始终保留。

分钟/日线直接提供 code、date、open/high/low/close、volume、amount；日线额外展开 PE/PB、市值、股本、换手、量比、ST 等。代码保持字符串与前导零；date 保留源整数；trade_date 只是从源 date 拆出 YYYYMMDD，不重定位分钟 bar。

```python
import duckdb
root = '/Users/simon/Trading/下载数据/stockdb_parquet'
con = duckdb.connect()
rows = con.execute(f"""
    SELECT source_db, code, date, open, high, low, close, volume, amount
    FROM read_parquet('{root}/tables/daily_bars/*.parquet')
    WHERE code = '000001' ORDER BY date, source_db
""").df()
```

## 去重、口径与停止条件

- 只在同 source_db 内按 sequence 取最新，应用 tombstone；data/data1 均含业务数据，不假设是不同资产域，不默认推断覆盖优先级。
- kidx: 是可重建二级索引，不作为业务行导出；退市队列 meta/seq 和未知辅助 KV 保留。旧 SST 不在当前 MANIFEST 内，不是丢失的当前业务。
- 不捏造财务、Tick 或宏观表；本地没有不等于上游永远不支持。
- 不填零、不前向填充、不平移分钟标签、不合并前后复权、不偷偷换算 PE/PB；保留原值，疑点进入 QC。
- 输出剩余磁盘低于 30 GiB 停止。最多 4 个工作进程，批量 65536 行；每个源键范围独立 checkpoint，临时文件不发布。
- 同版本脚本、同快照重跑会验证已完成 checkpoint 的输出 hash 并跳过；篡改或不同脚本/快照会拒绝复用。未完成任务留下的 `.partial` 不会自动覆盖；先核对精确任务后移到可恢复位置，或使用全新输出目录，不能广泛删除。
- 未证明权利/PIT/时标/生产者时，产物状态只到已校验的隔离包，不是正式 accepted/production。
- 本轮市场质量发现与恢复：源值 134228 条 MessagePack incomplete input，已单列可按证券/日期键查询的原字节异常表，原生查询代表样本也返回 null。旧日线 pre_close 大量不一致、少量 OHLC 异常及分钟空字段，均保留并显示 QC 标记。原库恢复前 692 个有效输入文件 hash 对齐，查询服务恢复 PID 20849，7 个精确键与 Parquet 一致；不代表全部原始字段适合回测。

## 2026-09-05 官方 Mac 包重装后的 SDK 核验

- 官方 latest 包内 44 个非数据文件与原安装一致。主程序 0.3.1 和更新器 0.3.2 是官方包实际组件号；只重装同内容 App 不会生成新的行情记录或补全旧截断值。
- 应用切换前备份到 /Users/simon/备份/codex/20260905-stockdb-macos-install.pu1Tfc。只启动主 App，不运行更新器或附带一键修复脚本，不替换现有 SDK/配置/数据库。当前 GUI 33497、server 33505；旧 PID 20849 只属于上一阶段。
- 本轮按发行包文档走官方 SDK 的显式 table/code/date 精确读取，warm=False；不绕道远程 get_price/get_bars/get_ticks，也不沿用旧全局 keys 扫描。CSV/JSON/Parquet 是用户明确请求的文件导出，不是另建供应商策略内部数据库。
- 一次性小样与运行命令见 /Users/simon/Trading/下载数据/stockdb_native_export_check_20260905/README.md；sandbox 只放行 localhost:7899 与小样输出目录。验证器在输出已存在时拒绝重跑，禁止为重新运行而静默覆盖证据。
- 9 键中 7 可读、2 null；正常结果已写成 Parquet 并重开/对账，但源质量未通过。既有全量导出不变，没有联网补到新日期，也没有完成异常修复；不要再启动一次全量扫描来证明相同二进制能够读取相同数据。

## 2026-09-05 后续隔离异常处理

用户已另行授权异常修复；上述“未修复”仅指此前同内容重装阶段。当前结果、独立读取方法、Grok 回传/根代理复核及回滚统一见 /Users/simon/Trading/下载数据/stockdb_repair_20260905/README.md；实施权威条目为 /Users/simon/Trading/one-trading/docs/data-platform-development-log.md#stockdb-isolated-repair。

重现使用 scripts/repair_stockdb_records.py（输入坏值 Parquet + 全新输出目录，支持 --dry-run）和 scripts/repair_stockdb_preclose.py（全新输出目录；--codes 可先做固定证券 canary）。不要改冻结的原始导出器或旧归档以便复跑，不要给截断 MsgPack 补任意字节，不要重新打开原生引擎快照。

字段恢复的 successful marker 在 prefix_v1/validation.json，前收盘候选在 preclose_full_v1/validation.json。前者证明完整原字段被读出，后者只证明保守计算规则和源字段关系；两者都不代表独立价格真值、完整量额、事件/PIT 或生产准入。读取 pre_close_for_analysis 必须保留候选标志，不把它悄悄更名覆盖原 pre_close。源行情访问规则、单位和事件门仍有效。
