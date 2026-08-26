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
from datetime import UTC, datetime

from .decode import decode_first
from .model import InvokeStats, TimelineEvent, WciAnalysis, WorkerSetChange
from .util import event_kind, event_time, hhmmss, short, short_error

# Scaling triggers (what caused a scale action).
TRIGGER_PUSH = "task-add push (no-sync-match)"
TRIGGER_PULL = "PullStats poll"
TRIGGER_PLAN = "deferred planning"
TRIGGER_REGISTER = "task-queue registration"
TRIGGER_UNKNOWN = "unknown"


def _trigger(wtceid, wft_batch, wft_has_la, wft_la_eid):
    """(label, trigger_event_id) for the workflow task (by its completed-event id)
    that scheduled a scaling action: a local-activity marker = task-add push;
    otherwise the activity completion(s) / signal(s) that woke the task. Joins
    genuinely mixed tasks rather than guessing. The event id is the representative
    triggering event to deep-link to."""
    batch = list(wft_batch.get(wtceid) or [])  # list of (label, event_id)
    labels = [lbl for lbl, _ in batch]
    if wft_has_la.get(wtceid):
        labels.insert(0, TRIGGER_PUSH)
    labels = list(dict.fromkeys(labels))
    label = TRIGGER_UNKNOWN if not labels else (labels[0] if len(labels) == 1 else " + ".join(labels))
    # Prefer a push signal event, else the first trigger event, else the local-
    # activity marker, else the deciding workflow-task-completed event itself.
    eid = next((e for lbl, e in batch if lbl == TRIGGER_PUSH), None)
    if eid is None:
        eid = batch[0][1] if batch else wft_la_eid.get(wtceid) or wtceid
    return label, eid


def _ms_to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except Exception:
        return None


def _per_minute(times):
    buckets = collections.Counter(t.strftime("%Y-%m-%dT%H:%M") for t in times)
    return sorted(buckets.items())


def analyze_wci(build_id, runs, draining_start=None, drained_at=None) -> WciAnalysis:
    wfid = runs[0].workflow_id if runs else ""
    src = f"wci:{short(build_id, 8)}"

    invoke_links = []  # (time, run_id, trigger_event_id) per InvokeWorker
    started = completed = failed = 0
    pullstats = 0
    other: collections.Counter = collections.Counter()
    backlog_series = []
    last_scale_up: datetime | None = None
    worker_set_series = []  # list[WorkerSetChange] — Cloud Run / ECS sizing
    ws_meta = {}  # scheduled_event_id -> (size, trigger_label, trigger_eid, run_id)
    validate_failures = []  # (time, message) — ValidateSpec activity failures
    invoke_by_trigger: collections.Counter = collections.Counter()

    for r in runs:
        inv_ids = set()
        sched_name = {}
        # Trigger attribution keyed by workflow-task-completed event id: each scaling
        # activity records the WFT that scheduled it (workflow_task_completed_event_id).
        # We classify that WFT by (a) its own local-activity marker = task-add push, and
        # (b) the events that woke it (its "trigger batch": the activity completions /
        # signals appended since the previous WFT). We keep the triggering event ids so
        # the timeline can deep-link to them.
        wft_batch: dict = {}  # wft_completed_event_id -> list[(label, event_id)]
        wft_has_la: dict = {}  # wft_completed_event_id -> bool (LocalActivity ran)
        wft_la_eid: dict = {}  # wft_completed_event_id -> local-activity marker event id
        current_wft = None
        pending = []  # [(label, event_id)] accumulating for the next WFT

        for ev in r.history.events:
            which, att = event_kind(ev)
            t = event_time(ev)
            if which == "marker_recorded_event_attributes":
                # HandleTaskAddSignal is the only local activity -> no-sync-match push.
                if att.marker_name == "LocalActivity" and current_wft is not None:
                    wft_has_la[current_wft] = True
                    wft_la_eid.setdefault(current_wft, ev.event_id)
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
                    label, teid = _trigger(wtceid, wft_batch, wft_has_la, wft_la_eid)
                    invoke_by_trigger[label] += 1
                    invoke_links.append((t, r.run_id, teid))
                elif nm == "PullStats":
                    pullstats += 1
                elif nm == "UpdateWorkerSetSize":
                    inp = decode_first(list(att.input.payloads))
                    size = inp.get("updated_size") if isinstance(inp, dict) else None
                    label, teid = _trigger(wtceid, wft_batch, wft_has_la, wft_la_eid)
                    ws_meta[ev.event_id] = (size, label, teid, r.run_id)
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
                    size, label, teid, run_id = ws_meta.get(sid, (None, TRIGGER_UNKNOWN, None, r.run_id))
                    worker_set_series.append(WorkerSetChange(t, size, "ok", label, run_id, teid))
                elif nm == "PullStats":
                    pending.append((TRIGGER_PULL, ev.event_id))
                    resp = decode_first(list(att.result.payloads))
                    if isinstance(resp, dict):
                        for grp, st in (resp.get("scaling_status") or {}).items():
                            if isinstance(st, dict):
                                backlog_series.append((t, grp, st))
                                lsu = _ms_to_dt(st.get("last_scale_up_time_ms"))
                                if lsu and (last_scale_up is None or lsu > last_scale_up):
                                    last_scale_up = lsu
                elif nm == "HandleDeferredScalingDecision":
                    pending.append((TRIGGER_PLAN, ev.event_id))
                elif nm == "InvokeWorkersToRegisterTaskQueues":
                    pending.append((TRIGGER_REGISTER, ev.event_id))
            elif which == "activity_task_failed_event_attributes":
                sid = att.scheduled_event_id
                nm = sched_name.get(sid)
                if sid in inv_ids:
                    failed += 1
                elif nm == "UpdateWorkerSetSize":
                    size, label, teid, run_id = ws_meta.get(sid, (None, TRIGGER_UNKNOWN, None, r.run_id))
                    worker_set_series.append(
                        WorkerSetChange(t, size, f"FAILED: {short_error(att.failure.message)}", label, run_id, teid)
                    )
                elif nm == "ValidateSpec":
                    validate_failures.append((t, att.failure.message, r.run_id, sid))
            elif which == "workflow_execution_signaled_event_attributes":
                other[f"signal:{att.signal_name}"] += 1
                if att.signal_name == "task-add-signal":
                    pending.append((TRIGGER_PUSH, ev.event_id))

    worker_set_series.sort(key=lambda c: c.time)
    last_ws = next((c.size for c in reversed(worker_set_series) if c.status == "ok"), None)

    invoke_links.sort(key=lambda x: x[0])
    invoke_times = [x[0] for x in invoke_links]
    if invoke_times and last_scale_up is None:
        last_scale_up = invoke_times[-1]

    def _after(cutoff):
        return sum(1 for t in invoke_times if cutoff and t > cutoff)

    inv = InvokeStats(
        total=len(invoke_times),
        started=started,
        completed=completed,
        failed=failed,
        first=invoke_times[0] if invoke_times else None,
        last=invoke_times[-1] if invoke_times else None,
        per_minute=_per_minute(invoke_times),
        peak_per_min=max((c for _, c in _per_minute(invoke_times)), default=0),
        after_draining_start=_after(draining_start),
        after_drained=_after(drained_at),
        by_trigger=dict(invoke_by_trigger),
        first_run=invoke_links[0][1] if invoke_links else None,
        first_event_id=invoke_links[0][2] if invoke_links else None,
        last_run=invoke_links[-1][1] if invoke_links else None,
        last_event_id=invoke_links[-1][2] if invoke_links else None,
    )

    terminal = _terminal(runs)
    events = _events(src, wfid, runs, inv, terminal, worker_set_series)
    for t, msg, run_id, sid in validate_failures:
        events.append(TimelineEvent(t, src, wfid, run_id, f"ValidateSpec FAILED: {short_error(msg)}", event_id=sid))
    return WciAnalysis(
        build_id=build_id,
        workflow_id=wfid,
        runs=len(runs),
        invoke=inv,
        pullstats_count=pullstats,
        other_activities=dict(other),
        last_scale_up=last_scale_up,
        terminal=terminal,
        backlog_series=backlog_series,
        events=events,
        worker_set_series=worker_set_series,
        last_worker_set_size=last_ws,
        validate_failures=validate_failures,
    )


def _terminal(runs) -> str | None:
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
        ev.append(
            TimelineEvent(
                inv.first,
                src,
                wfid,
                inv.first_run or "",
                f"first InvokeWorker (of {inv.total})",
                event_id=inv.first_event_id,
            )
        )
    if inv.last:
        ev.append(
            TimelineEvent(
                inv.last,
                src,
                wfid,
                inv.last_run or "",
                f"last InvokeWorker (total {inv.total}, {inv.failed} failed)",
                event_id=inv.last_event_id,
            )
        )
    for ch in worker_set_series:
        ev.append(
            TimelineEvent(
                ch.time,
                src,
                wfid,
                ch.run_id,
                f"UpdateWorkerSetSize -> {ch.size} ({ch.status}) [trigger: {ch.trigger}]",
                event_id=ch.trigger_event_id,
            )
        )
    if runs:
        final = runs[-1]
        last = final.history.events[-1]
        ev.append(
            TimelineEvent(
                event_time(last), src, wfid, final.run_id, f"WCI chain ended: {terminal}", event_id=last.event_id
            )
        )
    return ev
