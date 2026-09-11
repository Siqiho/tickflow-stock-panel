# 启动日志静态快照（终态）

持续追加的 stdout 已改到隔离 `DATA_DIR/logs/news-p2-backend.log` 与 `news-p2-frontend.log`。本文件是迁出前的静态摘录，不再追加。p2-fix 不再放 live stdout。

- 摘录截止：2026-09-09T18:01+08（迁出前）
- 完整 live 日志：`/Users/simon/Trading/one-trading/data/news-isolated-20260909/logs/`
- 迁出前副本 sha256：backend `f7a0a32ba65830b0759b959fcf6f10ef4bd2655b186ac7d8a219196bda48cd14`；frontend `e6bc77c2222ca546a7480314318defe3f2a8a932fe6ceaeae5764a53bdcdc5fe`

## 央行刷新（PID 93005）

```
INFO:     Started server process [93005]
INFO:     Uvicorn running on http://127.0.0.1:3048 (Press CTRL+C to quit)
2026-09-09 17:54:17,086 [INFO] httpx: HTTP Request: GET http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html "HTTP/1.1 302 Moved Temporarily"
2026-09-09 17:54:17,178 [INFO] httpx: HTTP Request: GET https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html "HTTP/1.1 200 OK"
INFO:     127.0.0.1:65005 - "POST /api/news/policy/refresh HTTP/1.1" 200 OK
INFO:     Finished server process [93005]
```

## 去重修法重启（PID 94803）与 3041

```
----- restart after title-dedupe fix 2026-09-09T17:56:02+0800 -----
INFO:     Started server process [94803]
INFO:     Uvicorn running on http://127.0.0.1:3048 (Press CTRL+C to quit)
  VITE v5.4.21  ready in 108 ms
  ➜  Local:   http://127.0.0.1:3041/
```

轮询/后续 GET 行不收入本快照，避免候选指纹随访问变化。

## 日志迁出后当前进程（2026-09-09T18:02+08）

- 3048 PID `97934` → `DATA_DIR/logs/news-p2-backend.log`
- 3041 PID `97951` → `DATA_DIR/logs/news-p2-frontend.log`
- p2-fix 的 `backend-3048.log` / `frontend-3041.log` 已移入废纸篓，不再作为候选 live 文件。
