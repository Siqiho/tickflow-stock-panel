# 数据源接线再审计（2026-09-12 follow-up）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/fix-data-source-wiring-6c07` / PR #2 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: remaining preference / fetch / label mismatches after the first wiring fix. Writes now go to server prefs, custom daily sync honors `daily_data_provider`, leftover TickFlow-free adj actually runs the public adapter (and is labeled as such), realtime product default stays `public` unless TickFlow is chosen explicitly.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| `PUT /preferences/data-providers` | `preferences.save()` 写账户文件 | getters 读 `load_server()`，租户目录与 owner home 不一致时 UI 切换无效 |
| `get_full_minute_data_provider` | 读 `load()` | 与其它市场源分轨，后台任务与账号偏好可能各读各的 |
| 日 K 同步 | 永远走 TickFlow `sync_daily_batch` | 设置页选了扶摇/自定义日 K，盘后管道仍打 TickFlow；`test_fuyao_daily_streaming_sync` 已写契约 |
| 盘后除权门槛 | `has(ADJ_FACTOR) or is_public` 才调用 `sync_adj_factor` | 上一轮加的「无 TickFlow 复权能力 → 公开新浪 qfq」死在门槛外 |
| 能力表 / 除权标签 | leftover tickflow + 无 cap → `source=none` | 实际会走公开源，UI 说没有复权 |
| 实时默认 | 注册表 / 前端 DEFAULT_ROUTING = `tickflow`，getter 默认 `public` | 「恢复默认」或套用无实时能力的源会把公开实时改成 TickFlow，free 档变 `mode=none` |
| 财务步骤 | `financial_provider === 'public'` | `eastmoney` / `em` / `free` 已是公开财务，数据页管道步骤不显示「财务」 |
| TickFlow 内置 datasets | 只有 daily/adj/realtime/minute | 五档 / 财务在矩阵里有、源清单里没有 |
| 能力矩阵 adj | API 注入已自愈的 getter | 存量 `same_as_daily` 不再显示「跟随日K」 |

## 改了什么

1. **settings**：`update_data_providers` / 删除源回写走 `save_server()`；删除实时源回退 `public`。
2. **preferences**：`full_minute` 读 server；新增 `get_adj_factor_provider_stored()` 给矩阵展示。
3. **kline_sync**：`daily_data_provider` 指向声明了 daily 的自定义/插件源时走 `iter_daily` / `get_daily` + staging 落盘；TickFlow 路径仍要 `kline.daily.batch`。
4. **daily_pipeline**：除权不再因档位不足跳过；公开适配器（显式或 leftover）用 `public_data_scope` 限流。
5. **capabilities / 能力表**：无 TickFlow 复权 cap 时报 `public_fallback`；实时注册表默认 `public`。
6. **UI**：恢复默认 ≠ 套用 TickFlow；财务别名；TickFlow datasets 补 depth5/financial。

未改：盘后默认时刻、分钟全市场、`.env`、鉴权、备份/原包。实时 leftover TickFlow + free 仍是 `mode=none`（不静默改走公开源）。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-followup \
  .venv/bin/python -B -m pytest -q \
    tests/test_data_source_write_path.py \
    tests/test_custom_daily_routing.py \
    tests/test_fuyao_daily_streaming_sync.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_pipeline_pull_types.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_realtime_mode.py \
    tests/test_capability_matrix.py \
    tests/test_capability_augment.py \
    tests/test_minute_availability.py \
    tests/test_financial_provider_preference.py
```

前端：

```
cd frontend && npm test -- --run src/lib/dataSources.test.ts
```
