"""Render the consolidated timeline, drain summary, and per-WCI metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .model import DeploymentAnalysis, VersionAnalysis, WciAnalysis
from .util import DEFAULT_UI_BASE, cloud_url, dt_str, hhmmss, iso, short

_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _blocked_builds(dep: DeploymentAnalysis):
    return {b.build_id for b in dep.delete_blocks}


def _val(v) -> str:
    if v.validation_ok is True:
        return "PASS"
    if v.validation_ok is False:
        return "**FAILED**"
    return "—"


def _render_validation(L, versions, wcis):
    """Per-version compute-provider validation status, loudly flagging failures."""
    L.append("## Version validation")
    any_fail = any_pass = False
    for b, v in versions.items():
        provider = v.provider_type or "?"
        if v.validation_ok is True:
            any_pass = True
            L.append(f"- {short(b)} [{provider}]: **PASS** (last checked {dt_str(v.validation_last_check)})")
        elif v.validation_ok is False:
            any_fail = True
            L.append(f"- {short(b)} [{provider}]: **FAILED** — {v.validation_error} "
                     f"(last checked {dt_str(v.validation_last_check)})")
        else:
            L.append(f"- {short(b)} [{provider}]: validation status unknown (no compute_status)")
        # Historical ValidateSpec activity failures seen in the controller.
        w = wcis.get(b)
        vf = (w.validate_failures if w else None) or []
        if vf:
            any_fail = True
            L.append(f"    - {len(vf)} ValidateSpec activity failure(s); first {dt_str(vf[0][0])}: "
                     f"{vf[0][1].splitlines()[0][:200]}")
    if versions and any_pass and not any_fail:
        L.append("")
        L.append("_All checked versions passed compute-provider validation._")
    L.append("")


def _histogram(per_minute, peak) -> List[str]:
    lines = []
    mx = peak or 1
    for m, c in per_minute:
        # m is "YYYY-MM-DDTHH:MM" -> "MM-DD HH:MM" (date kept for multi-day windows)
        label = m[5:16].replace("T", " ")
        bar = "#" * round(c / mx * 30)
        lines.append(f"  {label}  {c:>4}  {bar}")
    return lines


def build_report(
    deployment: str,
    dep: DeploymentAnalysis,
    versions: Dict[str, VersionAnalysis],
    wcis: Dict[str, WciAnalysis],
    win_start: Optional[datetime],
    win_end: Optional[datetime],
    namespace: Optional[str] = None,
    link_groups: Optional[List] = None,
    ui_base: str = DEFAULT_UI_BASE,
    poller_statuses: Optional[List] = None,
) -> tuple:
    L: List[str] = []
    blocked = _blocked_builds(dep)
    poller_statuses = poller_statuses or []

    L.append(f"# WCI forensics — {deployment}")
    L.append(f"Window: {iso(win_start)} .. {iso(win_end)}")
    L.append("")

    warnings = _warnings(versions, poller_statuses)
    if warnings:
        L.append("## ⚠️ Warnings")
        for w in warnings:
            L.append(f"- {w}")
        L.append("")

    L.append("## Current-version transitions")
    L.append("| time (UTC) | from | to |")
    L.append("|---|---|---|")
    for tr in dep.transitions:
        L.append(f"| {hhmmss(tr.at)} | {short(tr.from_build)} | {short(tr.to_build)} |")
    L.append("")

    L.append("## Drain summary")
    L.append("| build | serverless | validation | became current | draining start | drained | deleted | delete-blocked (pollers) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for b, v in versions.items():
        L.append(
            f"| {short(b)} | {'yes' if v.serverless else 'no'} | {_val(v)} | {hhmmss(v.became_current)} "
            f"| {hhmmss(v.draining_start)} | {hhmmss(v.drained_at)} | {hhmmss(v.deleted_at)} "
            f"| {'YES' if b in blocked else 'no'} |"
        )
    L.append("")

    _render_validation(L, versions, wcis)

    if dep.delete_blocks:
        L.append("## Delete-version blocked by active pollers")
        L.append("| time (UTC) | build | reason |")
        L.append("|---|---|---|")
        for db in dep.delete_blocks:
            L.append(f"| {hhmmss(db.at)} | {short(db.build_id)} | {db.reason} |")
        L.append("")

    for b, w in wcis.items():
        v = versions.get(b)
        inv = w.invoke
        provider = (v.provider_type if v else None) or "unknown"
        L.append(f"## WCI metrics — {short(b)} [{provider}] ({w.runs} runs)")
        L.append(f"- InvokeWorker invocations (Lambda invoke-strategy): **{inv.total}** "
                 f"(started {inv.started} / completed {inv.completed} / failed {inv.failed})")
        if inv.by_trigger:
            triggers = ", ".join(f"{k}: {v}" for k, v in sorted(inv.by_trigger.items(), key=lambda kv: -kv[1]))
            L.append(f"- Invokes by trigger: {triggers}")
        L.append(f"- Window: {hhmmss(inv.first)} .. {hhmmss(inv.last)}  |  peak {inv.peak_per_min}/min  "
                 f"|  last scale-up {hhmmss(w.last_scale_up)}")
        if v:
            L.append(f"- Invokes AFTER draining start ({hhmmss(v.draining_start)}): **{inv.after_draining_start}**  "
                     f"|  AFTER drained ({hhmmss(v.drained_at)}): **{inv.after_drained}**")
        if w.worker_set_series:
            L.append(f"- **Worker pool size (instances)** — set via `UpdateWorkerSetSize`; last set to "
                     f"**{w.last_worker_set_size}** ({len(w.worker_set_series)} change(s)):")
            for t, size, status, trigger in w.worker_set_series:
                L.append(f"    - {dt_str(t)}  size={size}  ({status})  ← trigger: {trigger}")
        L.append(f"- PullStats polls: {w.pullstats_count}  |  other: {w.other_activities}")
        L.append(f"- Chain terminated: {w.terminal}")
        if inv.per_minute:
            L.append("")
            L.append("InvokeWorker per minute:")
            L.append("```")
            L.extend(_histogram(inv.per_minute, inv.peak_per_min))
            L.append("```")
        L.append("")

    pollers_json = _render_pollers(L, poller_statuses)

    links_json = _render_links(L, namespace, link_groups or [], ui_base)

    L.append("## Consolidated timeline")
    L.append("| datetime (UTC) | source | event | run |")
    L.append("|---|---|---|---|")
    for e in _merged_timeline(dep, versions, wcis):
        L.append(f"| {dt_str(e.time)} | {e.source} | {e.summary} | {e.run_id[:8]} |")
    L.append("")

    summary = _json_summary(deployment, dep, versions, wcis, win_start, win_end, blocked)
    summary["links"] = links_json
    summary["task_queue_pollers"] = pollers_json
    summary["warnings"] = warnings
    return "\n".join(L), summary


def _warnings(versions, poller_statuses):
    w = []
    for b, v in versions.items():
        if v.validation_ok is False:
            w.append(f"Version `{short(b)}` compute validation is **FAILING**: {v.validation_error}")
    for st in poller_statuses:
        if st.mismatches:
            vers = sorted({p.version for p in st.mismatches})
            w.append(
                f"Task queue `{st.task_queue}` has worker(s) polling on {vers} but its current "
                f"version is `{st.current_version}` — **those workers will not receive tasks** "
                f"(routing is version-pinned)."
            )
    return w


def _render_pollers(L, poller_statuses):
    L.append("## Task-queue pollers / version match")
    out = {}
    if not poller_statuses:
        L.append("_no task queues checked (offline mode, or none discovered — pass `--task-queue`)._")
        L.append("")
        return out
    for st in poller_statuses:
        L.append(f"**{st.task_queue}** — current version: `{st.current_version}`")
        if st.error:
            L.append(f"- error: {st.error}")
        for p in st.pollers:
            flag = "  ⚠️ **MISMATCH**" if p in st.mismatches else ""
            L.append(f"- [{p.tq_type}] `{p.identity}` polling as `{p.version}` ({p.mode}){flag}")
        if not st.pollers:
            L.append("- (no active pollers)")
        if st.mismatches:
            L.append(f"  > ⚠️ {len(st.mismatches)} poller(s) are NOT on the current version "
                     f"`{st.current_version}`; tasks route to the current version, so these workers get nothing. "
                     f"Fix the worker's deployment name / build id (or set the current version to match).")
        L.append("")
        out[st.task_queue] = {
            "current_version": st.current_version,
            "error": st.error,
            "pollers": [
                {"identity": p.identity, "type": p.tq_type, "version": p.version,
                 "mode": p.mode, "mismatch": p in st.mismatches}
                for p in st.pollers
            ],
        }
    return out


def _render_links(L, namespace, link_groups, ui_base):
    """Append the Temporal Cloud links section; return the JSON representation."""
    L.append("## Temporal Cloud links")
    out = {}
    if not namespace:
        L.append("_pass `--namespace` to generate Temporal Cloud links._")
        L.append("")
        return out
    if not link_groups:
        L.append("_no runs to link._")
        L.append("")
        return out
    for label, wfid, runs in link_groups:
        wf_url = cloud_url(namespace, wfid, ui_base=ui_base)
        L.append(f"**{label}** — [`{wfid}`]({wf_url})")
        run_json = []
        for r in runs:
            url = cloud_url(namespace, wfid, r.run_id, ui_base=ui_base)
            L.append(f"- {hhmmss(r.start_time)}–{hhmmss(r.end_time)}  {url}")
            run_json.append({"run_id": r.run_id, "start": iso(r.start_time),
                             "end": iso(r.end_time), "url": url})
        L.append("")
        out[label] = {"workflow_id": wfid, "workflow_url": wf_url, "runs": run_json}
    return out


def _merged_timeline(dep, versions, wcis):
    events = list(dep.events)
    for v in versions.values():
        events.extend(v.events)
    for w in wcis.values():
        events.extend(w.events)
    events.sort(key=lambda e: (e.time or _MIN))
    return events


def _json_summary(deployment, dep, versions, wcis, win_start, win_end, blocked):
    return {
        "deployment": deployment,
        "window": {"start": iso(win_start), "end": iso(win_end)},
        "transitions": [
            {"at": iso(t.at), "from": t.from_build, "to": t.to_build} for t in dep.transitions
        ],
        "versions": {
            b: {
                "serverless": v.serverless,
                "provider": v.provider_type,
                "task_queues": v.task_queues,
                "became_current": iso(v.became_current),
                "demote_received": iso(v.demote_received),
                "draining_start": iso(v.draining_start),
                "drained_at": iso(v.drained_at),
                "deleted_at": iso(v.deleted_at),
                "delete_blocked_by_pollers": b in blocked,
                "validation": {
                    "ok": v.validation_ok,
                    "error": v.validation_error,
                    "last_check": iso(v.validation_last_check),
                },
            }
            for b, v in versions.items()
        },
        "wci": {
            b: {
                "runs": w.runs,
                "invoke": {
                    "total": w.invoke.total,
                    "started": w.invoke.started,
                    "completed": w.invoke.completed,
                    "failed": w.invoke.failed,
                    "first": iso(w.invoke.first),
                    "last": iso(w.invoke.last),
                    "peak_per_min": w.invoke.peak_per_min,
                    "after_draining_start": w.invoke.after_draining_start,
                    "after_drained": w.invoke.after_drained,
                    "per_minute": w.invoke.per_minute,
                    "by_trigger": w.invoke.by_trigger or {},
                },
                "pullstats_count": w.pullstats_count,
                "last_scale_up": iso(w.last_scale_up),
                "terminal": w.terminal,
                "other_activities": w.other_activities,
                "worker_set": {
                    "last_size": w.last_worker_set_size,
                    "changes": [
                        {"at": iso(t), "size": size, "status": status, "trigger": trigger}
                        for t, size, status, trigger in (w.worker_set_series or [])
                    ],
                },
            }
            for b, w in wcis.items()
        },
        "delete_blocks": [
            {"at": iso(db.at), "build": db.build_id, "reason": db.reason} for db in dep.delete_blocks
        ],
    }
