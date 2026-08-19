"""Shared helpers: timestamps, formatting, enum names, event access."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

DRAINAGE_STATUS = {0: "UNSPECIFIED", 1: "DRAINING", 2: "DRAINED"}

DEFAULT_UI_BASE = "https://cloud.temporal.io"


def cloud_url(namespace, workflow_id, run_id=None, ui_base=DEFAULT_UI_BASE) -> Optional[str]:
    """Temporal Cloud UI link for a workflow (or a specific run's history)."""
    if not namespace:
        return None
    base = (
        f"{ui_base.rstrip('/')}/namespaces/{quote(namespace, safe='')}"
        f"/workflows/{quote(workflow_id, safe='')}"
    )
    return f"{base}/{quote(run_id, safe='')}/history" if run_id else base


def ts(proto_ts) -> Optional[datetime]:
    """A google.protobuf.Timestamp -> aware datetime, or None if unset (zero)."""
    if proto_ts is None:
        return None
    if proto_ts.seconds == 0 and proto_ts.nanos == 0:
        return None
    return proto_ts.ToDatetime(tzinfo=timezone.utc)


def hhmmss(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M:%S.%f")[:-3] if dt else "-"


def dt_str(dt: Optional[datetime]) -> str:
    """Full UTC date + time, e.g. '2026-08-18 22:18:03.975'."""
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if dt else "-"


def iso(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else "-"


def short(build_id: Optional[str], n: int = 12) -> str:
    if not build_id:
        return "<none>"
    return build_id[:n]


def event_time(event) -> datetime:
    return event.event_time.ToDatetime(tzinfo=timezone.utc)


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


def build_from_version(deployment_version, legacy_string) -> Optional[str]:
    """Extract a build id from a WorkerDeploymentVersion message or legacy string."""
    if deployment_version is not None and deployment_version.build_id:
        return deployment_version.build_id
    if legacy_string:
        for sep in (":", "."):
            if sep in legacy_string:
                return legacy_string.rsplit(sep, 1)[1]
        return legacy_string
    return None
