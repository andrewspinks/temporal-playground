"""Version-workflow analyzer.

For a single build id, walks the version workflow's continue-as-new chain and
derives drainage start/finish, when it became current, when it was demoted, and
when it was deleted; plus whether it is serverless and on which task queues.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from .decode import decode_first
from .model import TimelineEvent, VersionAnalysis
from .util import (DRAINAGE_STATUS, event_kind, event_time, short,
                   started_input_payloads, ts)


def _provider(compute_config) -> Optional[str]:
    for grp in compute_config.scaling_groups.values():
        if grp.provider_type:
            return grp.provider_type
    return None


def analyze_version(build_id, runs) -> VersionAnalysis:
    wfid = runs[0].workflow_id if runs else ""
    events: List[TimelineEvent] = []
    src = f"version:{short(build_id, 8)}"

    serverless = False
    provider = None
    task_queues: set = set()
    became_current: Optional[datetime] = None
    draining_start: Optional[datetime] = None
    drained_at: Optional[datetime] = None
    demote_received: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    validation_ok: Optional[bool] = None
    validation_error: Optional[str] = None
    validation_last_check: Optional[datetime] = None

    for r in runs:
        args = decode_first(started_input_payloads(r.history))
        if args is None or isinstance(args, (dict, bytes)):
            continue
        vs = args.version_state
        if vs.HasField("compute_config"):
            serverless = True
            provider = provider or _provider(vs.compute_config)
        # Latest run wins (runs are oldest-first), so this reflects current status.
        if vs.HasField("compute_status") and vs.compute_status.HasField("provider_validation"):
            pv = vs.compute_status.provider_validation
            validation_error = pv.error_message or None
            validation_ok = validation_error is None
            validation_last_check = ts(pv.last_check_time)
        cs = ts(vs.current_since_time)
        if cs and became_current is None:
            became_current = cs
        task_queues.update(vs.task_queue_families.keys())

        di = vs.drainage_info
        status = DRAINAGE_STATUS.get(di.status, str(di.status))
        changed = ts(di.last_changed_time)
        if status == "DRAINING" and changed and draining_start is None:
            draining_start = changed
        if status == "DRAINED" and changed and drained_at is None:
            drained_at = changed

        # In-workflow events: demote-version received signal, deletion.
        for ev in r.history.events:
            which, att = event_kind(ev)
            if which == "workflow_execution_signaled_event_attributes" and att.signal_name == "demote-version":
                t = event_time(ev)
                demote_received = demote_received or t
                events.append(TimelineEvent(t, src, wfid, r.run_id, "recv-signal demote-version (draining begins)"))
            elif which == "workflow_execution_completed_event_attributes":
                deleted_at = event_time(ev)

    if draining_start:
        events.append(TimelineEvent(draining_start, src, wfid, "", "drainage status -> DRAINING"))
    if drained_at:
        events.append(TimelineEvent(drained_at, src, wfid, "", "drainage status -> DRAINED"))
    if deleted_at:
        events.append(TimelineEvent(deleted_at, src, wfid, "", "version workflow COMPLETED (deleted)"))
    if validation_ok is False:
        events.append(TimelineEvent(validation_last_check, src, wfid, "",
                                    f"compute validation FAILING: {validation_error}"))

    events.sort(key=lambda e: (e.time or datetime.min.replace(tzinfo=timezone.utc)))
    return VersionAnalysis(
        build_id=build_id, workflow_id=wfid, serverless=serverless, provider_type=provider,
        task_queues=sorted(task_queues), became_current=became_current,
        demote_received=demote_received, draining_start=draining_start,
        drained_at=drained_at, deleted_at=deleted_at, events=events,
        validation_ok=validation_ok, validation_error=validation_error,
        validation_last_check=validation_last_check,
    )
