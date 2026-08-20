"""Deployment-workflow analyzer.

Reconstructs the current/ramping routing timeline, the version transitions, the
set of versions in play during the window, which of them are serverless
(WCI-managed), and surfaces the orchestration events — including
``delete-version`` attempts blocked by active pollers.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

from .decode import decode_first, decode_payload
from .model import (CurrentTransition, DeleteBlock, DeploymentAnalysis,
                    TimelineEvent, VersionInPlay)
from .util import (build_from_version, event_kind, event_time, short,
                   short_error, started_input_payloads, ts)

_VERSION_RE = re.compile(r"([0-9a-f]{40})")

# Orchestration updates/signals worth putting on the timeline.
_INTERESTING_UPDATES = {
    "set-current-version", "set-ramping-version", "delete-version",
}
_INTERESTING_SIGNALS = {"sync-version-summary"}


def _routing_build(rc):
    cur_dv = rc.current_deployment_version if rc.HasField("current_deployment_version") else None
    ramp_dv = rc.ramping_deployment_version if rc.HasField("ramping_deployment_version") else None
    return (
        build_from_version(cur_dv, rc.current_version),
        ts(rc.current_version_changed_time),
        build_from_version(ramp_dv, rc.ramping_version),
        rc.ramping_version_percentage,
        ts(rc.ramping_version_changed_time),
    )


def _provider_of(compute_config) -> Optional[str]:
    for grp in compute_config.scaling_groups.values():
        if grp.provider_type:
            return grp.provider_type
    return None


def analyze_deployment(runs, win_start=None, win_end=None) -> DeploymentAnalysis:
    wfid = runs[0].workflow_id if runs else ""
    events: List[TimelineEvent] = []
    delete_blocks: List[DeleteBlock] = []
    versions: dict[str, VersionInPlay] = {}

    # (current_changed_time, build) samples for deriving transitions.
    current_samples: List[tuple] = []

    for r in runs:
        args = decode_first(started_input_payloads(r.history))
        if args is None or isinstance(args, (dict, bytes)):
            continue
        state = args.state
        rc = state.routing_config
        cur_build, cur_changed, ramp_build, ramp_pct, ramp_changed = _routing_build(rc)
        current_samples.append((cur_changed, cur_build))

        # Serverless / provider info from the versions map. Note the summary's
        # `version` is a legacy string ("<deployment>:<build>"), unlike the
        # version-workflow's message-typed `version` field.
        for key, summ in state.versions.items():
            build = build_from_version(None, summ.version) or build_from_version(None, key)
            if not build:
                continue
            serverless = summ.HasField("compute_config")
            provider = _provider_of(summ.compute_config) if serverless else None
            vp = versions.get(build)
            if vp is None:
                versions[build] = VersionInPlay(build, serverless, provider)
            else:
                vp.serverless = vp.serverless or serverless
                vp.provider_type = vp.provider_type or provider

        _collect_events(r, wfid, events, delete_blocks)

    transitions = _derive_transitions(current_samples)
    in_play = _versions_in_window(transitions, versions, win_start, win_end)
    events.sort(key=lambda e: (e.time or datetime.min.replace(tzinfo=timezone.utc)))
    return DeploymentAnalysis(wfid, transitions, in_play, delete_blocks, events)


def _collect_events(r, wfid, events, delete_blocks):
    pending_accepted: List[tuple] = []  # (time, name, event_id)
    for ev in r.history.events:
        which, att = event_kind(ev)
        t = event_time(ev)
        if which == "workflow_execution_update_accepted_event_attributes":
            name = att.accepted_request.input.name
            pending_accepted.append((t, name, ev.event_id))
        elif which == "workflow_execution_update_completed_event_attributes":
            outcome = att.outcome
            failed = outcome.HasField("failure")
            raw_msg = outcome.failure.message if failed else ""
            acc_time, name, acc_eid = pending_accepted.pop(0) if pending_accepted else (t, "?", ev.event_id)
            if name in _INTERESTING_UPDATES or failed:
                status = "FAILED: " + short_error(raw_msg) if failed else "ok"
                events.append(TimelineEvent(acc_time, "deployment", wfid, r.run_id,
                                            f"update {name} -> {status}", event_id=acc_eid))
            if name == "delete-version" and failed:
                m = _VERSION_RE.search(raw_msg)  # build id from the full message
                delete_blocks.append(DeleteBlock(acc_time, m.group(1) if m else None, short_error(raw_msg)))
        elif which == "signal_external_workflow_execution_initiated_event_attributes":
            tgt = att.workflow_execution.workflow_id
            m = _VERSION_RE.search(tgt)
            events.append(TimelineEvent(t, "deployment", wfid, r.run_id,
                                        f"signal {att.signal_name} -> {short(m.group(1)) if m else tgt}",
                                        event_id=ev.event_id))
        elif which == "workflow_execution_signaled_event_attributes":
            if att.signal_name in _INTERESTING_SIGNALS:
                events.append(TimelineEvent(t, "deployment", wfid, r.run_id,
                                            f"recv-signal {att.signal_name}", event_id=ev.event_id))


def _derive_transitions(samples) -> List[CurrentTransition]:
    # Collapse to ordered unique (changed_time, build) points.
    uniq = []
    for changed, build in samples:
        if not uniq or uniq[-1] != (changed, build):
            uniq.append((changed, build))
    uniq.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)))
    transitions = []
    prev_build = None
    for changed, build in uniq:
        if build != prev_build:
            transitions.append(CurrentTransition(changed, prev_build, build))
            prev_build = build
    return transitions


def _versions_in_window(transitions, versions, win_start, win_end):
    """Builds current at any point during the window (step function over transitions)."""
    if not transitions:
        return versions  # no routing info; return everything known
    lo = win_start or datetime.min.replace(tzinfo=timezone.utc)
    hi = win_end or datetime.max.replace(tzinfo=timezone.utc)
    in_play = {}
    for i, tr in enumerate(transitions):
        start = tr.at or datetime.min.replace(tzinfo=timezone.utc)
        end = transitions[i + 1].at if i + 1 < len(transitions) else datetime.max.replace(tzinfo=timezone.utc)
        end = end or datetime.max.replace(tzinfo=timezone.utc)
        if tr.to_build and start <= hi and end >= lo:
            in_play[tr.to_build] = versions.get(tr.to_build, VersionInPlay(tr.to_build, False, None))
    return in_play
