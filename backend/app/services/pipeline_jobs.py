"""异步盘后管道任务注册表 — 每个 job 独立 JSON 文件。

设计:
  - job_store/ 文件夹,每个 job 一个 {id}.json,最多保留 max_jobs 个文件
  - running/pending 状态的 job 仅存内存(高频读写)
  - succeeded/degraded/failed 后写入独立文件并从内存释放
  - 列表查询 = 内存中的活跃 job + 磁盘文件扫描,按时间排序
  - 单个查询 = 内存优先,没有则读磁盘
  - 创建新 job 前检查文件数量,>= max_jobs 时删除最老的文件
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.services.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

JobStatus = Literal["pending", "running", "succeeded", "degraded", "failed"]
ControlPlaneSink = Callable[[dict[str, Any]], None]

# 卡死判定阈值(秒)。语义是「进度停滞」而非「总时长」:
# running 期间只要 progress() 还在上报, 就永远不算卡死。
DEFAULT_JOB_TIMEOUT_S = 1200
LONG_JOB_TIMEOUT_S = 1800
# 总时长硬上限(兜底): 进度回调持续但永不结束的病态循环。
HARD_JOB_TIMEOUT_S = 12 * 3600
STALE_JOB_TIMEOUT_S = DEFAULT_JOB_TIMEOUT_S


class JobCancelledError(BaseException):
    """协作式取消。继承 BaseException, 避免被 ``except Exception`` 吞掉。"""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"job {job_id} 已取消")
        self.job_id = job_id


class CreateResult(str):
    """兼容本地 ``job_id = create()`` 与 908 ``job_id, is_new = create()``。"""

    is_new: bool

    def __new__(cls, job_id: str, is_new: bool = True):
        obj = str.__new__(cls, job_id)
        obj.is_new = bool(is_new)
        return obj

    def __iter__(self):
        yield str(self)
        yield self.is_new


_CANCEL_FLAG_MAX = 32
_CANCEL_FLAGS: dict[str, threading.Event] = {}
_CANCEL_FLAGS_LOCK = threading.Lock()


def request_cancel(job_id: str) -> bool:
    with _CANCEL_FLAGS_LOCK:
        ev = _CANCEL_FLAGS.get(job_id)
        if ev is None:
            ev = threading.Event()
            _CANCEL_FLAGS[job_id] = ev
            while len(_CANCEL_FLAGS) > _CANCEL_FLAG_MAX:
                _CANCEL_FLAGS.pop(next(iter(_CANCEL_FLAGS)))
        ev.set()
        return True


def is_cancelled(job_id: str) -> bool:
    ev = _CANCEL_FLAGS.get(job_id)
    return ev is not None and ev.is_set()


def _register_cancel_flag(job_id: str) -> None:
    with _CANCEL_FLAGS_LOCK:
        _CANCEL_FLAGS.setdefault(job_id, threading.Event())


def _raise_if_cancelled(job_id: str) -> None:
    if is_cancelled(job_id):
        raise JobCancelledError(job_id)


def terminal_status(result: dict[str, Any]) -> Literal["succeeded", "degraded"]:
    """Map a completed pipeline result to an honest quality-aware terminal state."""
    quality = result.get("quality") if isinstance(result, dict) else None
    return "succeeded" if isinstance(quality, dict) and quality.get("ok") is True else "degraded"


def _normalize_legacy_quality_status(job: dict[str, Any]) -> dict[str, Any]:
    """Present legacy false-quality successes honestly without rewriting history files."""
    result = job.get("result")
    quality = result.get("quality") if isinstance(result, dict) else None
    if job.get("status") == "succeeded" and isinstance(quality, dict) and quality.get("ok") is False:
        job = dict(job)
        job["status"] = "degraded"
    return job


def _default_store_dir() -> Path:
    from app.config import settings
    return settings.data_dir / "job_store"


_STORE_DIR = _default_store_dir()


class JobStore:
    def __init__(self, max_jobs: int = 50, store_dir: Path = _STORE_DIR) -> None:
        self._max_jobs = max_jobs
        self._store_dir = store_dir
        self._active_jobs: dict[str, dict[str, Any]] = {}   # running/pending
        self._active_id: str | None = None
        self._active_by_key: dict[str, str] = {}
        self._lock = threading.Lock()
        self._sink_owner_lock = threading.Lock()
        self._control_plane_sink: ControlPlaneSink | None = None
        self._control_plane_sink_token: object | None = None
        self._sink_owners: dict[object, ControlPlaneSink] = {}
        self._sink_owner_order: list[object] = []
        self._mirror_metadata: dict[str, dict[str, str]] = {}
        self._mirror_owner_tokens: dict[str, object] = {}
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def set_control_plane_sink(self, sink: ControlPlaneSink | None) -> object | None:
        """Install a best-effort sink and return the ownership token for its cleanup."""
        if sink is None:
            return None
        token = object()
        with self._sink_owner_lock:
            self._sink_owners[token] = sink
            self._sink_owner_order.append(token)
            self._control_plane_sink = sink
            self._control_plane_sink_token = token
        return token

    def clear_control_plane_sink(self, token: object | None) -> bool:
        """Terminate this owner's mirrors, then clear only its installed sink.

        The legacy job remains active and may still finish into its JSON store.  Its
        control-plane projection, however, belongs to this lifespan and must not be
        left permanently running after that owner exits.
        """
        with self._sink_owner_lock:
            if token is None or token not in self._sink_owners:
                return False
            sink = self._sink_owners[token]
            with self._lock:
                owned_job_ids = [
                    job_id
                    for job_id, owner_token in self._mirror_owner_tokens.items()
                    if owner_token is token
                ]
                aborted: list[dict[str, Any]] = []
                for job_id in owned_job_ids:
                    job = self._active_jobs.get(job_id)
                    metadata = self._mirror_metadata.pop(job_id, None)
                    self._mirror_owner_tokens.pop(job_id, None)
                    if job is None or metadata is None:
                        continue
                    payload = dict(job)
                    payload.update(
                        status="failed",
                        finished_at=datetime.now(UTC)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z"),
                        error="control-plane owner shutdown",
                    )
                    payload["duration_s"] = _duration_s(payload)
                    payload["_catalog_mirror"] = dict(metadata)
                    payload["_catalog_error_code"] = "control_plane_owner_shutdown"
                    aborted.append(payload)
            for payload in aborted:
                try:
                    sink(payload)
                except Exception:
                    logger.exception(
                        "control-plane owner shutdown mirror failed: job_id=%s",
                        payload.get("id"),
                    )
            del self._sink_owners[token]
            self._sink_owner_order.remove(token)
            if self._sink_owner_order:
                current_token = self._sink_owner_order[-1]
                self._control_plane_sink_token = current_token
                self._control_plane_sink = self._sink_owners[current_token]
            else:
                self._control_plane_sink = None
                self._control_plane_sink_token = None
            return True

    def _notify_control_plane(
        self,
        job: dict[str, Any],
        mirror: Mapping[str, str] | None,
        owner_token: object | None,
        *,
        lock_held: bool = False,
    ) -> None:
        if mirror is None or owner_token is None:
            return
        payload = dict(job)
        payload["_catalog_mirror"] = dict(mirror)

        def dispatch() -> None:
            sink = self._sink_owners.get(owner_token)
            if sink is None:
                return
            try:
                sink(payload)
            except Exception:
                logger.exception("control-plane job mirror failed: job_id=%s", job.get("id"))

        # Terminal handoff already owns this lock so owner cleanup cannot pass
        # between removing the active job and publishing its terminal callback.
        if lock_held:
            dispatch()
        else:
            with self._sink_owner_lock:
                dispatch()

    # ===== persistence =====

    def _write_file(self, job: dict[str, Any]) -> None:
        """将终态 job 写入独立 JSON 文件。"""
        path = self._store_dir / f"{job['id']}.json"
        try:
            atomic_write_json(job, path)
        except Exception:
            logger.warning("failed to write job file %s", path)

    def _read_file(self, job_id: str) -> dict[str, Any] | None:
        """从磁盘读取单个 job 文件。"""
        path = self._store_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return _normalize_legacy_quality_status(json.loads(path.read_text("utf-8")))
        except Exception:
            logger.warning("failed to read job file %s", path)
            return None

    def _delete_oldest(self) -> None:
        """删除最老的 job 文件,保持文件数量 < max_jobs。"""
        try:
            files = sorted(self._store_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
        except Exception:
            return
        while len(files) >= self._max_jobs:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except Exception:
                logger.warning("failed to delete old job file %s", oldest)

    def _job_files_sorted(self) -> list[dict[str, Any]]:
        """扫描磁盘上所有 job 文件,按 started_at 从新到旧排序。"""
        jobs: list[dict[str, Any]] = []
        for f in self._store_dir.glob("*.json"):
            try:
                jobs.append(_normalize_legacy_quality_status(json.loads(f.read_text("utf-8"))))
            except Exception:
                continue
        jobs.sort(key=lambda j: j.get("started_at") or "", reverse=True)
        return jobs

    # ===== lifecycle =====

    @staticmethod
    def _work_identity(
        *,
        work_key: str | None,
        mirror: Mapping[str, str] | None,
    ) -> str:
        from app.services import user_context

        owner = str(user_context.current().get("id") or "owner")
        if work_key:
            body = str(work_key)
        elif mirror:
            body = f"{mirror.get('dataset_id', '')}|{mirror.get('operation', '')}"
        else:
            body = "default"
        return f"{owner}|{body}"

    def create(
        self,
        timeout_s: int | None = None,
        *,
        mirror: Mapping[str, str] | None = None,
        long_running: bool = False,
        work_key: str | None = None,
    ) -> CreateResult:
        """单飞创建。查找+创建在同一把锁内。

        同一 work identity 在 pending/running 窗口复用; 终态后可新建。
        不同 work_key / mirror operation / 用户 id 不合并。
        返回值是 str, 也可解包为 (job_id, is_new)。
        """
        if timeout_s is None:
            from app.services import preferences
            if long_running:
                timeout_s = preferences.get_data_source_long_job_timeout_s()
            else:
                timeout_s = preferences.get_data_source_job_timeout_s()

        identity = self._work_identity(work_key=work_key, mirror=mirror)
        with self._sink_owner_lock:
            owner_token = self._control_plane_sink_token if mirror is not None else None
            with self._lock:
                existing_id = self._active_by_key.get(identity)
                if existing_id:
                    active = self._active_jobs.get(existing_id)
                    if active and active.get("status") in ("pending", "running"):
                        return CreateResult(existing_id, False)

                job_id = uuid.uuid4().hex[:10]
                self._active_jobs[job_id] = {
                    "id": job_id,
                    "status": "pending",
                    "stage": "init",
                    "progress": 0,
                    "stage_pct": 0,
                    "log": [],
                    "started_at": None,
                    "last_progress_at": None,
                    "finished_at": None,
                    "duration_s": None,
                    "result": None,
                    "error": None,
                    "timeout_s": timeout_s,
                    "_work_key": identity,
                }
                if mirror is not None and owner_token is not None:
                    self._mirror_metadata[job_id] = dict(mirror)
                    self._mirror_owner_tokens[job_id] = owner_token
                self._active_by_key[identity] = job_id
                self._active_id = job_id
                created = dict(self._active_jobs[job_id])
                mirror_metadata = self._mirror_metadata.get(job_id)
        _register_cancel_flag(job_id)
        self._notify_control_plane(created, mirror_metadata, owner_token)
        return CreateResult(job_id, True)

    def start(self, job_id: str) -> None:
        _raise_if_cancelled(job_id)
        with self._lock:
            j = self._active_jobs.get(job_id)
            if not j:
                return
            j["status"] = "running"
            started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            j["started_at"] = started_at
            j["last_progress_at"] = started_at
            started = dict(j)
            mirror_metadata = self._mirror_metadata.get(job_id)
            owner_token = self._mirror_owner_tokens.get(job_id)
        self._notify_control_plane(started, mirror_metadata, owner_token)

    def succeed(self, job_id: str, result: Any) -> None:
        self._finish(job_id, status="succeeded", result=result)

    def degrade(self, job_id: str, result: Any) -> None:
        self._finish(job_id, status="degraded", result=result)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        """Finish a daily pipeline using its quality report as the authority."""
        self._finish(job_id, status=terminal_status(result), result=result)

    def _finish(
        self,
        job_id: str,
        *,
        status: Literal["succeeded", "degraded"],
        result: Any,
    ) -> None:
        with self._sink_owner_lock:
            with self._lock:
                j = self._active_jobs.pop(job_id, None)
                if not j:
                    return
                j["status"] = status
                j["finished_at"] = (
                    datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                )
                j["progress"] = 100
                j["result"] = result
                j["duration_s"] = _duration_s(j)
                if self._active_id == job_id:
                    self._active_id = None
                key = j.get("_work_key")
                if key and self._active_by_key.get(key) == job_id:
                    self._active_by_key.pop(key, None)
                self._delete_oldest()
                self._write_file(j)
                finished = dict(j)
                mirror_metadata = self._mirror_metadata.get(job_id)
                owner_token = self._mirror_owner_tokens.get(job_id)
            self._notify_control_plane(
                finished,
                mirror_metadata,
                owner_token,
                lock_held=True,
            )
            with self._lock:
                if self._mirror_owner_tokens.get(job_id) is owner_token:
                    self._mirror_metadata.pop(job_id, None)
                    self._mirror_owner_tokens.pop(job_id, None)
        # 槽由执行体 finally 释放。终态记录不得在工作线程仍存活时放掉执行权。

    def fail(self, job_id: str, error: str) -> None:
        with self._sink_owner_lock:
            with self._lock:
                j = self._active_jobs.pop(job_id, None)
                if not j:
                    return
                j["status"] = "failed"
                j["finished_at"] = (
                    datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                )
                j["error"] = error
                j["duration_s"] = _duration_s(j)
                if self._active_id == job_id:
                    self._active_id = None
                key = j.get("_work_key")
                if key and self._active_by_key.get(key) == job_id:
                    self._active_by_key.pop(key, None)
                self._delete_oldest()
                self._write_file(j)
                failed = dict(j)
                mirror_metadata = self._mirror_metadata.get(job_id)
                owner_token = self._mirror_owner_tokens.get(job_id)
            self._notify_control_plane(
                failed,
                mirror_metadata,
                owner_token,
                lock_held=True,
            )
            with self._lock:
                if self._mirror_owner_tokens.get(job_id) is owner_token:
                    self._mirror_metadata.pop(job_id, None)
                    self._mirror_owner_tokens.pop(job_id, None)
        # 与 _finish 相同: 不在此释放 run slot, 避免取消/失败后旧工作仍在写时新任务入槽。

    def reap_stale(self, timeout_s: int | None = None) -> None:
        """回收卡死的 running job。两种判定:

        1. 进度停滞(主判定): 距上次 progress() 上报超过阈值秒数。
        2. 总时长硬上限(兜底): 进度回调持续但永不结束的病态循环。

        本地多用户: 扫描全部 running, 不只看单一 _active_id。
        终止是协作式的: 置 cancel flag → 僵尸在下一分块 progress() 抛
        JobCancelledError。卡死线程可能永远不回来, 因此 terminate 会按
        所有权释放执行槽; 手动取消仍不放槽 (工作线程还活着)。
        """
        with self._lock:
            candidates = [
                (jid, dict(job))
                for jid, job in self._active_jobs.items()
                if job.get("status") == "running" and job.get("started_at")
            ]
        for jid, job in candidates:
            started = job.get("started_at")
            last_alive = job.get("last_progress_at") or started
            if not started:
                continue
            effective_timeout = (
                timeout_s if timeout_s is not None
                else job.get("timeout_s", DEFAULT_JOB_TIMEOUT_S)
            )
            try:
                start_dt = _parse_utc(started)
                alive_dt = _parse_utc(last_alive)
                now = datetime.now(start_dt.tzinfo)
                stalled_s = (now - alive_dt).total_seconds()
                total_s = (now - start_dt).total_seconds()
            except Exception:  # noqa: BLE001
                continue
            if stalled_s > effective_timeout:
                logger.warning(
                    "reap_stale: 强制取消卡死 job %s (进度停滞 %.0fs > 阈值 %ss, 总运行 %.0fs)",
                    jid, stalled_s, effective_timeout, total_s,
                )
                self.terminate(
                    jid,
                    f"超时自动取消: 进度停滞 {int(stalled_s)}s 超过阈值 {effective_timeout}s,已请求终止",
                )
            elif total_s > HARD_JOB_TIMEOUT_S:
                logger.warning(
                    "reap_stale: 强制取消 job %s (总运行 %.0fs 超过硬上限 %ss)",
                    jid, total_s, HARD_JOB_TIMEOUT_S,
                )
                self.terminate(
                    jid,
                    f"超时自动取消: 总运行 {int(total_s)}s 超过硬上限,已请求终止",
                )

    def terminate(self, job_id: str, message: str) -> None:
        """标记失败 + 请求协作式终止 + 强制释放执行槽(带所有权)。

        仅供 reap_stale / 硬上限使用。卡死线程可能永远回不来释放槽;
        僵尸即使后续短暂写盘, 也会在下一个 progress() 自行退出。
        手动取消走 fail()+request_cancel(), 不经过这里, 以免活着的
        工作线程被新任务并发写入。
        """
        request_cancel(job_id)
        self.fail(job_id, message)
        release_run_slot(job_id)

    # ===== progress =====

    def progress(self, job_id: str, stage: str, pct: int, msg: str,
                 stage_pct: int | None = None, skip_log: bool = False) -> None:
        _raise_if_cancelled(job_id)
        with self._lock:
            j = self._active_jobs.get(job_id)
            if not j:
                return
            j["stage"] = stage
            j["progress"] = max(0, min(100, int(pct)))
            j["last_progress_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            if stage_pct is not None:
                j["stage_pct"] = max(0, min(100, int(stage_pct)))
            elif j["stage"] != stage:
                j["stage_pct"] = 0
            entry = {
                "ts": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "stage": stage,
                "msg": msg,
            }
            if skip_log:
                entry["_skip"] = True
            if skip_log and j["log"] and j["log"][-1].get("stage") == stage and j["log"][-1].get("_skip"):
                j["log"][-1] = entry
            else:
                j["log"].append(entry)
                if len(j["log"]) > 200:
                    j["log"] = j["log"][-200:]

    # ===== query =====

    def get(self, job_id: str) -> dict[str, Any] | None:
        # 内存中的活跃 job 优先
        j = self._active_jobs.get(job_id)
        if j:
            return j
        # 否则从磁盘读
        return self._read_file(job_id)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        # 合并: 内存中的活跃 job + 磁盘文件
        all_jobs: list[dict[str, Any]] = list(self._active_jobs.values())
        all_jobs.extend(self._job_files_sorted())
        # 按 started_at 从新到旧排序,去重(理论上不会有重复)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for j in sorted(all_jobs, key=lambda x: x.get("started_at") or "", reverse=True):
            jid = j["id"]
            if jid in seen:
                continue
            seen.add(jid)
            result.append(_summary(j))
            if len(result) >= limit:
                break
        return result

    def active_id(self) -> str | None:
        return self._active_id

    def clear(self) -> None:
        """清空所有任务（内存 + 磁盘文件）。"""
        with self._lock:
            self._active_jobs.clear()
            self._active_id = None
            self._active_by_key.clear()
            self._mirror_metadata.clear()
            self._mirror_owner_tokens.clear()
            for f in self._store_dir.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass


def _summary(j: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": j["id"],
        "status": j["status"],
        "stage": j["stage"],
        "progress": j["progress"],
        "stage_pct": j.get("stage_pct", 0),
        "started_at": j["started_at"],
        "finished_at": j["finished_at"],
        "duration_s": j["duration_s"],
        "result": j["result"],
        "error": j["error"],
    }


def _parse_utc(ts: str) -> datetime:
    """解析 start()/progress() 存的 "2026-07-04T12:00:00Z" 形式时间戳。"""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _duration_s(j: dict[str, Any]) -> float | None:
    if not j.get("started_at") or not j.get("finished_at"):
        return None
    try:
        s = datetime.fromisoformat(j["started_at"])
        e = datetime.fromisoformat(j["finished_at"])
        return round((e - s).total_seconds(), 2)
    except Exception:  # noqa: BLE001
        return None


# 进程内单例
job_store = JobStore()


# 重任务执行槽: 绑定实际执行体。create 单飞按 work identity;
# 槽在 start 前获取, fail/succeed/cancel 的 finally 释放。
_run_slot_lock = threading.Lock()
_run_slot_owner: str | None = None


def try_acquire_run_slot(owner: str = "") -> bool:
    """尝试占用重任务执行槽(非阻塞)。成功返回 True 并记录持有者。"""
    global _run_slot_owner
    with _run_slot_lock:
        if _run_slot_owner is not None:
            return False
        _run_slot_owner = owner
        return True


def release_run_slot(owner: str | None = None) -> None:
    """释放重任务执行槽。owner 非 None 且不是当前持有者时忽略。"""
    global _run_slot_owner
    with _run_slot_lock:
        if owner is not None and _run_slot_owner is not None and _run_slot_owner != owner:
            return
        _run_slot_owner = None
