# 独立复查入口

只审本目录，不要把主树既有脏文件算进本轮。`review/` 是上一轮独立复查的原始证据，只读。

1. 读 `README.md`、`APPLY.md`、`fixes-response.md`
2. 审 `patches/phase-b-industry-fflow-daily-roll.diff`（现为六文件：原四文件 + `pipeline.py` + `ext_data.py`）
3. 对照 `overlay/` 与 `baseline/`
4. 复跑 `APPLY.md` 里的隔离测试（原 12 + 返工回归 + overlay vitest）
5. 主树四个源文件 SHA 应仍等于 `baseline/SHA256.txt` 顶部四行，除非复查者自己已应用补丁
6. 不要改 `review/tests/test_independent_findings.py`；那些用例断言的是返工前的旧行为

不要 commit / push / 部署 / 写正式 DATA_DIR / 重启 3018。
