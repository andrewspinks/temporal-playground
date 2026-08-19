"""WCI (worker-controller-instance) analyzer — the measurement core.

Measures, for one serverless version's controller across its CAN chain:
  - InvokeWorker (Lambda) invocations: total + scheduled/started/completed/failed,
    per-minute frequency, peak, and the count that occurred AFTER draining began /
    AFTER the version drained (the key correlation).
  - PullStats cadence and the scaling-metric (rate/worker-count) time series.
  - How the controller chain terminated.
"""
from __future__ import annotations

import collections
from datetime import datetime, timezone
from typing import Optional

from .decode import decode_first
from .model import InvokeStats, TimelineEvent, WciAnalysis
from .util import event_kind, event_time, hhmmss, short


# Scaling triggers (what caused a scale action).
TRIGGER_PUSH = "task-add push (no-sync-match)"
TRIGGER_PULL = "PullStats poll"
TRIGGER_PLAN = "deferred planning"
TRIGGER_REGISTER = "task-queue registration"
TRIGGER_UNKNOWN = "unknown"


def _classify(wtceid, wft_batch, wft_has_la) -> str:
    """Trigger for the workflow task (by its completed-event id) that scheduled a
    scaling action: a local-activity marker means a task-add push; otherwise the
    activity completion(s) / signal(s) that woke the task. Joins genuinely mixed
    tasks rather than guessing."""
    labels = list(wft_batch.get(wtceid) or [])
    if wft_has_la.get(wtceid):
        labels.insert(0, TRIGGER_PUSH)
    labels = list(dict.fromkeys(labels))  # dedupe, preserve order
    if not labels:
        return TRIGGER_UNKNOWN
    return labels[0] if len(labels) == 1 else " + ".join(labels)


def _ms_to_dt(ms) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except Exception:
        return None


def _per_minute(times):
    buckets = collections.Counter(t.strftime("%Y-%m-%dT%H:%M") for t in times)
    return sorted(buckets.items())


def analyze_wci(build_id, runs, draining_start=None, drained_at=None) -> WciAnalysis:
    wfid = runs[0].workflow_id if runs else ""
    src = f"wci:{short(build_id, 8)}"

    invoke_times = []
    started = completed = failed = 0
    pullstats = 0
    other: collections.Counter = collections.Counter()
    backlog_series = []
    last_scale_up: Optional[datetime] = None
    worker_set_series = []  # (time, size, status, trigger) — Cloud Run / ECS sizing
    ws_size = {}       # scheduled_event_id -> requested size
    ws_trigger = {}    # scheduled_event_id -> trigger label
    validate_failures = []  # (time, message) — ValidateSpec activity failures
    invoke_by_trigger: collections.Counter = collections.Counter()

    for r in runs:
        inv_ids = set()
        sched_name = {}
        # Trigger attribution keyed by workflow-task-completed event id: each scaling
        # activity records the WFT that scheduled it (workflow_task_completed_event_id).
        # We classify that WFT by (a) its own local-activity marker = task-add push, and
        # (b) the events that woke it (its "trigger batch": the activity completions /
        # signals appended since the previous WFT).
        wft_batch: dict = {}     # wft_completed_event_id -> list of trigger labels
        wft_has_la: dict = {}    # wft_completed_event_id -> bool (LocalActivity ran)
        current_wft = None
        pending = []             # trigger labels accumulating for the next WFT

        for ev in r.history.events:
            which, att = event_kind(ev)
            t = event_time(ev)
            if which == "marker_recorded_event_attributes":
                # HandleTaskAddSignal is the only local activity -> no-sync-match push.
                if att.marker_name == "LocalActivity" and current_wft is not None:
                    wft_has_la[current_wft] = True
            elif which == "workflow_task_completed_event_attributes":
                current_wft = ev.event_id
                wft_batch[current_wft] = pending
                wft_has_la.setdefault(current_wft, False)
                pending = []
            elif which == "activity_task_scheduled_event_attributes":
                nm = att.activity_type.name
                sched_name[ev.event_id] = nm
                wtceid = att.workflow_task_completed_event_id
                if nm == "InvokeWorker":
                    inv_ids.add(ev.event_id)
                    invoke_times.append(t)
                    invoke_by_trigger[_classify(wtceid, wft_batch, wft_has_la)] += 1
                elif nm == "PullStats":
                    pullstats += 1
                elif nm == "UpdateWorkerSetSize":
                    inp = decode_first(list(att.input.payloads))
                    ws_size[ev.event_id] = inp.get("updated_size") if isinstance(inp, dict) else None
                    ws_trigger[ev.event_id] = _classify(wtceid, wft_batch, wft_has_la)
                    other[nm] += 1
                else:
                    other[nm] += 1
            elif which == "activity_task_started_event_attributes":
                if att.scheduled_event_id in inv_ids:
                    started += 1
            elif which == "activity_task_completed_event_attributes":
                sid = att.scheduled_event_id
                nm = sched_name.get(sid)
                if sid in inv_ids:
                    completed += 1
                elif nm == "UpdateWorkerSetSize":
                    worker_set_series.append((t, ws_size.get(sid), "ok", ws_trigger.get(sid, TRIGGER_UNKNOWN)))
                elif nm == "PullStats":
                    pending.append(TRIGGER_PULL)
                    resp = decode_first(list(att.result.payloads))
                    if isinstance(resp, dict):
                        for grp, st in (resp.get("scaling_status") or {}).items():
                            if isinstance(st, dict):
                                backlog_series.append((t, grp, st))
                                lsu = _ms_to_dt(st.get("last_scale_up_time_ms"))
                                if lsu and (last_scale_up is None or lsu > last_scale_up):
                                    last_scale_up = lsu
                elif nm == "HandleDeferredScalingDecision":
                    pending.append(TRIGGER_PLAN)
                elif nm == "InvokeWorkersToRegisterTaskQueues":
                    pending.append(TRIGGER_REGISTER)
            elif which == "activity_task_failed_event_attributes":
                sid = att.scheduled_event_id
                nm = sched_name.get(sid)
                if sid in inv_ids:
                    failed += 1
                elif nm == "UpdateWorkerSetSize":
                    worker_set_series.append((t, ws_size.get(sid), f"FAILED: {att.failure.message}", ws_trigger.get(sid, TRIGGER_UNKNOWN)))
                elif nm == "ValidateSpec":
                    validate_failures.append((t, att.failure.message))
            elif which == "workflow_execution_signaled_event_attributes":
                other[f"signal:{att.signal_name}"] += 1
                if att.signal_name == "task-add-signal":
                    pending.append(TRIGGER_PUSH)

    worker_set_series.sort(key=lambda x: x[0])
    last_ws = next((s for _, s, st, _ in reversed(worker_set_series) if st == "ok"), None)

    invoke_times.sort()
    if invoke_times and last_scale_up is None:
        last_scale_up = invoke_times[-1]

    def _after(cutoff):
        return sum(1 for t in invoke_times if cutoff and t > cutoff)

    inv = InvokeStats(
        total=len(invoke_times), started=started, completed=completed, failed=failed,
        first=invoke_times[0] if invoke_times else None,
        last=invoke_times[-1] if invoke_times else None,
        per_minute=_per_minute(invoke_times),
        peak_per_min=max((c for _, c in _per_minute(invoke_times)), default=0),
        after_draining_start=_after(draining_start),
        after_drained=_after(drained_at),
        by_trigger=dict(invoke_by_trigger),
    )

    terminal = _terminal(runs)
    events = _events(src, wfid, runs, inv, terminal, worker_set_series)
    for t, msg in validate_failures:
        events.append(TimelineEvent(t, src, wfid, "", f"ValidateSpec FAILED: {msg}"))
    return WciAnalysis(
        build_id=build_id, workflow_id=wfid, runs=len(runs), invoke=inv,
        pullstats_count=pullstats, other_activities=dict(other),
        last_scale_up=last_scale_up, terminal=terminal,
        backlog_series=backlog_series, events=events,
        worker_set_series=worker_set_series, last_worker_set_size=last_ws,
        validate_failures=validate_failures,
    )


def _terminal(runs) -> Optional[str]:
    if not runs:
        return None
    final = runs[-1]
    last = final.history.events[-1]
    which, _ = event_kind(last)
    end = which.replace("_event_attributes", "").replace("workflow_execution_", "").upper()
    detail = ""
    if which == "workflow_execution_completed_event_attributes":
        # Surface the last activity failure that typically triggers shutdown.
        for ev in reversed(final.history.events):
            w, att = event_kind(ev)
            if w == "activity_task_failed_event_attributes":
                detail = f" (last activity failure: {att.failure.message})"
                break
    return f"{end} at {hhmmss(event_time(last))}{detail}"


def _events(src, wfid, runs, inv: InvokeStats, terminal, worker_set_series) -> list:
    ev = []
    if inv.first:
        ev.append(TimelineEvent(inv.first, src, wfid, "", f"first InvokeWorker (of {inv.total})"))
    if inv.last:
        ev.append(TimelineEvent(inv.last, src, wfid, "", f"last InvokeWorker (total {inv.total}, {inv.failed} failed)"))
    for t, size, status, trigger in worker_set_series:
        ev.append(TimelineEvent(t, src, wfid, "",
                                f"UpdateWorkerSetSize -> {size} ({status}) [trigger: {trigger}]"))
    if runs:
        final = runs[-1]
        last_t = event_time(final.history.events[-1])
        ev.append(TimelineEvent(last_t, src, wfid, final.run_id, f"WCI chain ended: {terminal}"))
    return ev
