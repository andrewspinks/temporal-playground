"""Shared helpers: timestamps, formatting, enum names, event access."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import quote

DRAINAGE_STATUS = {0: "UNSPECIFIED", 1: "DRAINING", 2: "DRAINED"}


def short_error(msg: str | None, limit: int = 160) -> str:
    """Condense a failure message to a single readable line. Full detail (stack
    traces, embedded JSON) is reachable via the event's Cloud link, so keep only
    the first line up to any embedded blob, collapsed and length-capped."""
    if not msg:
        return msg or ""
    first = msg.strip().splitlines()[0]
    first = first.split(" {", 1)[0].rstrip(" :{").strip()  # drop trailing JSON/struct blob
    first = re.sub(r"\s+", " ", first)
    return first if len(first) <= limit else first[: limit - 1] + "…"


DEFAULT_UI_BASE = "https://cloud.temporal.io"


def cloud_url(namespace, workflow_id, run_id=None, ui_base=DEFAULT_UI_BASE) -> str | None:
    """Temporal Cloud UI link for a workflow (or a specific run's history)."""
    if not namespace:
        return None
    base = f"{ui_base.rstrip('/')}/namespaces/{quote(namespace, safe='')}/workflows/{quote(workflow_id, safe='')}"
    return f"{base}/{quote(run_id, safe='')}/history" if run_id else base


def cloud_event_url(namespace, workflow_id, run_id, event_id, ui_base=DEFAULT_UI_BASE) -> str | None:
    """Temporal Cloud UI link to a specific history event within a run.

    Route: /namespaces/<ns>/workflows/<wf>/<run>/history/events/<eventId>
    """
    if not (namespace and run_id and event_id):
        return None
    return f"{cloud_url(namespace, workflow_id, run_id, ui_base)}/events/{event_id}"


def ts(proto_ts) -> datetime | None:
    """A google.protobuf.Timestamp -> aware datetime, or None if unset (zero)."""
    if proto_ts is None:
        return None
    if proto_ts.seconds == 0 and proto_ts.nanos == 0:
        return None
    return proto_ts.ToDatetime(tzinfo=UTC)


def hhmmss(dt: datetime | None) -> str:
    return dt.strftime("%H:%M:%S.%f")[:-3] if dt else "-"


def dt_str(dt: datetime | None) -> str:
    """Full UTC date + time, e.g. '2026-08-18 22:18:03.975'."""
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if dt else "-"


def iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else "-"


def short(build_id: str | None, n: int = 12) -> str:
    if not build_id:
        return "<none>"
    return build_id[:n]


def event_time(event) -> datetime:
    return event.event_time.ToDatetime(tzinfo=UTC)


def event_kind(event):
    """Return (which_oneof_name, attributes_message) for a HistoryEvent."""
    which = event.WhichOneof("attributes")
    return which, (getattr(event, which) if which else None)


def started_input_payloads(history):
    """Payloads of the WorkflowExecutionStarted input (event 1)."""
    att = history.events[0].workflow_execution_started_event_attributes
    if att.HasField("input"):
        return list(att.input.payloads)
    return []


def build_from_version(deployment_version, legacy_string) -> str | None:
    """Extract a build id from a WorkerDeploymentVersion message or legacy string."""
    if deployment_version is not None and deployment_version.build_id:
        return deployment_version.build_id
    if legacy_string:
        for sep in (":", "."):
            if sep in legacy_string:
                return legacy_string.rsplit(sep, 1)[1]
        return legacy_string
    return None
