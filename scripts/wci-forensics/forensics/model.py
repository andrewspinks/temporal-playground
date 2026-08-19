"""Shared result/timeline data structures consumed by the report layer."""
from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Dict, List, Optional


@dataclasses.dataclass
class TimelineEvent:
    time: Optional[datetime]
    source: str  # 'deployment' | 'version:<build8>' | 'wci:<build8>'
    workflow_id: str
    run_id: str
    summary: str


@dataclasses.dataclass
class VersionInPlay:
    build_id: str
    serverless: bool
    provider_type: Optional[str] = None


@dataclasses.dataclass
class CurrentTransition:
    at: Optional[datetime]
    from_build: Optional[str]
    to_build: Optional[str]
    via_ramp: bool = False


@dataclasses.dataclass
class DeleteBlock:
    at: datetime
    build_id: Optional[str]
    reason: str


@dataclasses.dataclass
class DeploymentAnalysis:
    workflow_id: str
    transitions: List[CurrentTransition]
    versions_in_play: Dict[str, VersionInPlay]
    delete_blocks: List[DeleteBlock]
    events: List[TimelineEvent]


@dataclasses.dataclass
class VersionAnalysis:
    build_id: str
    workflow_id: str
    serverless: bool
    provider_type: Optional[str]
    task_queues: List[str]
    became_current: Optional[datetime]
    demote_received: Optional[datetime]
    draining_start: Optional[datetime]
    drained_at: Optional[datetime]
    deleted_at: Optional[datetime]
    events: List[TimelineEvent]
    # Compute-provider validation (from version_state.compute_status.provider_validation).
    # validation_ok is None when unknown (e.g. non-serverless / no compute_status).
    validation_ok: Optional[bool] = None
    validation_error: Optional[str] = None
    validation_last_check: Optional[datetime] = None


@dataclasses.dataclass
class InvokeStats:
    total: int
    started: int
    completed: int
    failed: int
    first: Optional[datetime]
    last: Optional[datetime]
    per_minute: List  # list[(minute_str, count)]
    peak_per_min: int
    after_draining_start: int
    after_drained: int
    by_trigger: Dict = None  # trigger label -> invoke count


@dataclasses.dataclass
class WciAnalysis:
    build_id: str
    workflow_id: str
    runs: int
    invoke: InvokeStats
    pullstats_count: int
    other_activities: Dict[str, int]
    last_scale_up: Optional[datetime]
    terminal: Optional[str]  # how the WCI chain ended (completed reason, etc.)
    backlog_series: List  # list[(time, group, backlog/rate dict)]
    events: List[TimelineEvent]
    # Worker-set launch strategy (Cloud Run / ECS): instance-count changes over time.
    worker_set_series: List = None  # list[(time, size, status)]
    last_worker_set_size: Optional[int] = None
    # ValidateSpec activity failures observed over the WCI chain: list[(time, message)].
    validate_failures: List = None
