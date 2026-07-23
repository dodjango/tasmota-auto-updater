"""In-memory background job runner for long-running batch firmware updates.

A batch firmware update can take minutes per device. Running it inside the HTTP
request blocks a worker for the whole batch and trips the Gunicorn request
timeout. Instead, the API creates a job here, runs it on a background thread and
returns ``202 Accepted`` immediately; clients poll ``GET /api/jobs/<id>`` for
progress and results.

Job state lives in this process's memory, guarded by a lock. This assumes a
single Gunicorn worker (see ``gunicorn.conf.py``); scaling to multiple workers
would require a shared store (e.g. Redis).
"""
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.tasmota.updater import update_device_firmware

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}

# Keep at most this many finished jobs around (small LAN tool; avoid unbounded growth).
_MAX_JOBS = 50


def _snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy safe to serialise outside the lock."""
    snap = dict(job)
    snap["results"] = list(job["results"])
    return snap


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return a serialisable snapshot of a job, or None if unknown."""
    with _lock:
        job = _jobs.get(job_id)
        return _snapshot(job) if job else None


def batch_in_progress() -> bool:
    with _lock:
        return any(j["status"] in ("pending", "running") for j in _jobs.values())


def _prune_locked() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    finished = [
        (jid, j) for jid, j in _jobs.items()
        if j["status"] in ("completed", "error")
    ]
    finished.sort(key=lambda kv: kv[1].get("finished_at") or 0)
    for jid, _ in finished[: len(_jobs) - _MAX_JOBS]:
        _jobs.pop(jid, None)


def create_batch_job(
    devices: List[Dict[str, Any]],
    check_only: bool,
    update_only_needed: bool,
    global_timeout: Optional[int],
    *,
    updater: Optional[Callable[..., Dict[str, Any]]] = None,
    clock: Callable[[], float] = time.time,
    background: bool = True,
) -> Optional[str]:
    """Create and start a batch job. Returns the job id, or None if one is already running.

    ``updater``/``clock``/``background`` are injectable to keep the runner testable.
    The updater defaults to the module-level ``update_device_firmware`` resolved at
    call time (so it can be monkeypatched in tests).
    """
    resolved_updater = updater or update_device_firmware
    with _lock:
        if any(j["status"] in ("pending", "running") for j in _jobs.values()):
            return None
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "check_only": bool(check_only),
            "total": 0,
            "completed": 0,
            "failed": 0,
            "results": [],
            "summary": None,
            "error": None,
            "created_at": clock(),
            "finished_at": None,
        }
        _prune_locked()

    if background:
        threading.Thread(
            target=_run_batch,
            args=(job_id, devices, check_only, update_only_needed, global_timeout, resolved_updater, clock),
            daemon=True,
        ).start()
    else:
        _run_batch(job_id, devices, check_only, update_only_needed, global_timeout, resolved_updater, clock)
    return job_id


def _set(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(fields)


def _run_batch(
    job_id: str,
    devices: List[Dict[str, Any]],
    check_only: bool,
    update_only_needed: bool,
    global_timeout: Optional[int],
    updater: Callable[..., Dict[str, Any]],
    clock: Callable[[], float],
) -> None:
    try:
        _set(job_id, status="running")

        # Determine which devices to process (mirrors the previous sync endpoint).
        if update_only_needed and not check_only:
            devices_to_process = [
                d for d in devices
                if updater(d.copy(), check_only=True).get("needs_update", False)
            ]
        else:
            devices_to_process = list(devices)
        _set(job_id, total=len(devices_to_process))

        results: List[Dict[str, Any]] = []
        updated = 0
        for device in devices_to_process:
            config = device.copy()
            if global_timeout is not None:
                config["timeout"] = global_timeout
            result = updater(config, check_only)
            result["update_started"] = (
                not check_only and (result.get("needs_update", False) or not update_only_needed)
            )
            result["update_completed"] = bool(result.get("success")) and result["update_started"]
            if result["update_completed"]:
                updated += 1
            results.append(result)
            with _lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job["completed"] = len(results)
                    job["failed"] = sum(
                        1 for r in results if r.get("update_started") and not r.get("success")
                    )
                    job["results"] = list(results)

        summary = {
            "total": len(devices),
            "processed": len(devices_to_process),
            "success": sum(1 for r in results if r.get("success")),
            "needs_update": sum(1 for r in results if r.get("needs_update", False)),
            "updated": updated,
        }
        _set(job_id, status="completed", summary=summary, finished_at=clock())
    except Exception as exc:  # pragma: no cover - defensive; surfaced to the client
        _set(job_id, status="error", error=str(exc), finished_at=clock())


def _reset_for_tests() -> None:
    """Clear all job state (test helper)."""
    with _lock:
        _jobs.clear()
