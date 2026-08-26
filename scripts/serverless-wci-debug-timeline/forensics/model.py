"""Shared result/timeline data structures consumed by the report layer."""

from __future__ import annotations

import dataclasses
from datetime import datetime


@dataclasses.dataclass
class TimelineEvent:
    time: datetime | None
    source: str  # 'deployment' | 'version:<build8>' | 'wci:<build8>'
    workflow_id: str
    run_id: str
    summary: str
    # The history event this row links to (the triggering event, where known).
    event_id: int | None = None


@dataclasses.dataclass
class WorkerSetChange:
    time: datetime | None
    size: int | None
    status: str
    trigger: str
    run_id: str
    trigger_event_id: int | None = None


@dataclasses.dataclass
class VersionInPlay:
    build_id: str
    serverless: bool
    provider_type: str | None = None


@dataclasses.dataclass
class CurrentTransition:
    at: datetime | None
    from_build: str | None
    to_build: str | None
    via_ramp: bool = False


@dataclasses.dataclass
class DeleteBlock:
    at: datetime
    build_id: str | None
    reason: str


@dataclasses.dataclass
class DeploymentAnalysis:
    workflow_id: str
    transitions: list[CurrentTransition]
    versions_in_play: dict[str, VersionInPlay]
    delete_blocks: list[DeleteBlock]
    events: list[TimelineEvent]


@dataclasses.dataclass
class VersionAnalysis:
    build_id: str
    workflow_id: str
    serverless: bool
    provider_type: str | None
    task_queues: list[str]
    became_current: datetime | None
    demote_received: datetime | None
    draining_start: datetime | None
    drained_at: datetime | None
    deleted_at: datetime | None
    events: list[TimelineEvent]
    # Compute-provider validation (from version_state.compute_status.provider_validation).
    # validation_ok is None when unknown (e.g. non-serverless / no compute_status).
    validation_ok: bool | None = None
    validation_error: str | None = None
    validation_last_check: datetime | None = None


@dataclasses.dataclass
class InvokeStats:
    total: int
    started: int
    completed: int
    failed: int
    first: datetime | None
    last: datetime | None
    per_minute: list  # list[(minute_str, count)]
    peak_per_min: int
    after_draining_start: int
    after_drained: int
    by_trigger: dict = None  # trigger label -> invoke count
    # Trigger event of the first / last invoke (for timeline deep-links).
    first_run: str | None = None
    first_event_id: int | None = None
    last_run: str | None = None
    last_event_id: int | None = None


@dataclasses.dataclass
class WciAnalysis:
    build_id: str
    workflow_id: str
    runs: int
    invoke: InvokeStats
    pullstats_count: int
    other_activities: dict[str, int]
    last_scale_up: datetime | None
    terminal: str | None  # how the WCI chain ended (completed reason, etc.)
    backlog_series: list  # list[(time, group, backlog/rate dict)]
    events: list[TimelineEvent]
    # Worker-set launch strategy (Cloud Run / ECS): instance-count changes over time.
    worker_set_series: list = None  # list[(time, size, status)]
    last_worker_set_size: int | None = None
    # ValidateSpec activity failures observed over the WCI chain: list[(time, message)].
    validate_failures: list = None
