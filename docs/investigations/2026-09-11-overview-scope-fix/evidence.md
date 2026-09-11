# WP2 overview-scope 紧凑证据

续接 `dce105e3` / candidate `010200b5bfcdc050ea221e2032f0c870ce5e53869b73bc299318859bb3c849f7`。旧 wf `69099e44` blocked。备份 `/Users/simon/备份/codex/20260911-170040-overview-scope-fix-before`。

## 检查

| 命令 | 结果 |
| --- | --- |
| pytest 五文件 | 27 passed |
| vitest scope+multiuser+Layout.mobile | 43 passed |
| tsc --noEmit | exit 0 |
| vite /tmp/ot-overview-scope-vite-dist | 成功，未写 shared dist |
| /tmp repro 5 旧样本 | unknown + null 合计 + sample 4/0/1 / 5572000000 |

## 等待

- 独立 review
- owner `01a07a79-1c8e-73e0-af8f-85939177bb8b` 刷新 3018
- Codex IAB
- 不是 accepted / production

## 声明文件 SHA256（日志/本文件写入后）

```
2aaff324b7b4b3ffb6a775a1431f03fdd324dd9e56b0038b3c196fce7365efc6  backend/app/api/overview.py
a5947f3daae90a71a656b222427c13c5d5544ddce7ce21527c04af1e2d0445ea  backend/app/services/intraday_overview.py
3d3b3a4071c4c1866481830673720f6ac58b54dfd88233814fd0c8b859aeb27a  backend/app/services/market_overview_builder.py
837c9a50f84fee891974b120aac1a150ca3ee9c4c1b1ef187f2825ba7eae7320  backend/app/services/quote_service.py
63f1eef23482553ed1bf6fc16febf75899eaa7367ad4b17fd68a3f9290226cce  backend/tests/test_intraday_overview.py
0e4c85fae3f81806e618c853a94221a131eb53cfc73cb2c8ca38062c8c575c11  backend/tests/test_market_overview_as_of.py
e47e20e59cfc99c7d93743373f15990a20158139f6a3ff379de22865e8215762  backend/tests/test_overview_scope.py
1c4c9dd42a462a57177d3f0bd21e71ff5ee16ad5b88258d9a9adb5ad36f77646  backend/tests/test_quote_service_interval.py
9668b7acd083e1e4986e12a0d4fb0eb3a134bc2fbbc0e134d3a2a92d090913e8  backend/tests/test_quote_service_watchlist_union.py
6121ec6b646ab4eb7fa482b9123a37f310eda40f8ee8100c8f4dec320f81541b  docs/data-platform-development-log.md
29359b4615dae01ccae574e74c59c77d194f1b98f91a7a63781281ae233ef441  docs/investigations/2026-09-11-dashboard-data-acceptance/chief-acceptance.md
9d789fb41f028028fb7db830b1bf5fff634c9a40472081be280301cd9579f891  docs/investigations/2026-09-11-overview-scope-fix/fixtures/README.md
ef73c5a29fd36f709819dbaee833eb3b12aefa3fe16134d20c86ef4094d14b4a  docs/investigations/2026-09-11-overview-scope-fix/fixtures/old-quote-5-sample.json
9181a2761a1f49ae889d8ef8093bf58ceacce6dfdea87ce8dfb9285253d99813  docs/investigations/2026-09-11-overview-scope-fix/implementation.md
a5f5a4f5f75023299cadf7d20fbbbaa9d19a8665520058ba9b132424c79a29b5  docs/investigations/2026-09-11-overview-scope-fix/scripts/repro-old-quote-5-sample.py
06e5dcf149f6f328cd149aaab64395dbcb59fe2a01853fc6853ab03f5cdd8fa4  docs/workbench-development-log.md
12bf802cd562c5d0b545a54918962d8be71a8c260f23b870934733f670b7bcbe  frontend/src/components/Layout.tsx
e6f8e84b8cce0d063e5fdc130b9da4da39e4b26f3c8ff6638b6f649109876868  frontend/src/components/__tests__/Layout.mobile.test.tsx
d26c3d96b85113c0ca2083bfc6e3435ba0dcf5186a8f788f21db2fecb54601d2  frontend/src/lib/api.ts
0e8f20d4c23e36503ea1fb1f618c728d1bf6943396e2de5a176ae32d5a0bb027  frontend/src/pages/Dashboard.tsx
4ac8f85704e7579c668e8bbccc4b91f6e4ab9cdc11a4fff7efdb7392cb717034  frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx
485d5a0bd0cd37ed345e7d797af973700d1cee7f8b2553d8d977964ad5aebb50  frontend/src/pages/__tests__/Dashboard.scope.test.tsx
```

（`evidence.md` 自身在写入本表后会再变，以磁盘为准。）
