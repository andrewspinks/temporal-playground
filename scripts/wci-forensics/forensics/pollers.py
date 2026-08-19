"""Live poller / version-match check via DescribeTaskQueue.

Detects the classic "worker polls but never gets tasks" misconfiguration: a
worker polling a task queue with a build id / versioning identity that does not
match the task queue's *current* version. Worker Versioning routes tasks only to
the current version, so a mismatched worker sits polling and receives nothing.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest

from .util import ts

UNVERSIONED = "__unversioned__"

try:
    from temporalio.api.enums.v1 import WorkerVersioningMode
    _VERSIONED = WorkerVersioningMode.WORKER_VERSIONING_MODE_VERSIONED
except Exception:  # pragma: no cover
    _VERSIONED = 2


@dataclasses.dataclass
class Poller:
    identity: str
    tq_type: str
    version: str  # normalized "<deployment>:<build>" or "__unversioned__"
    mode: str
    last_access: Optional[object]


@dataclasses.dataclass
class TaskQueuePollerStatus:
    task_queue: str
    current_version: str
    pollers: List[Poller]
    mismatches: List[Poller]
    error: Optional[str] = None


def _norm(dep, build) -> str:
    return f"{dep}:{build}"


def _current_version(vinfo) -> str:
    if vinfo is None:
        return UNVERSIONED
    if vinfo.HasField("current_deployment_version"):
        dv = vinfo.current_deployment_version
        return _norm(dv.deployment_name, dv.build_id)
    s = vinfo.current_version or UNVERSIONED
    if s == UNVERSIONED:
        return UNVERSIONED
    for sep in (":", "."):  # legacy "<dep>:<build>" or "<dep>.<build>"
        if sep in s:
            d, b = s.rsplit(sep, 1)
            return _norm(d, b)
    return s


def _poller_version(p):
    if p.HasField("deployment_options") and p.deployment_options.deployment_name:
        do = p.deployment_options
        if do.worker_versioning_mode == _VERSIONED:
            return _norm(do.deployment_name, do.build_id), "VERSIONED"
        return UNVERSIONED, "UNVERSIONED"
    wvc = p.worker_version_capabilities
    if wvc and wvc.build_id:
        return (wvc.build_id, "VERSIONED(legacy)") if wvc.use_versioning else (UNVERSIONED, "UNVERSIONED")
    return UNVERSIONED, "UNVERSIONED"


async def check_task_queue(client, namespace, tq) -> TaskQueuePollerStatus:
    pollers: List[Poller] = []
    current = UNVERSIONED
    error = None
    for tqt, tname in ((TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW, "workflow"),
                       (TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY, "activity")):
        try:
            resp = await client.workflow_service.describe_task_queue(
                DescribeTaskQueueRequest(namespace=namespace, task_queue=TaskQueue(name=tq), task_queue_type=tqt)
            )
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:200]}"
            continue
        if resp.HasField("versioning_info"):
            current = _current_version(resp.versioning_info)
        for p in resp.pollers:
            ver, mode = _poller_version(p)
            pollers.append(Poller(p.identity, tname, ver, mode, ts(p.last_access_time)))
    mismatches = [p for p in pollers if p.version != current]
    return TaskQueuePollerStatus(tq, current, pollers, mismatches, error)
