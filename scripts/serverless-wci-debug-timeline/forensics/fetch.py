"""History sourcing: live (dial + cache) or offline (folder of dumps).

Both sources expose ``runs_for(workflow_id, start, end)`` returning the
continue-as-new runs of that workflow ID whose event span overlaps the window,
ordered oldest-first.
"""

from __future__ import annotations

import dataclasses
import glob
import os
import re
import sys
from datetime import UTC, datetime

from google.protobuf import json_format
from temporalio.api.history.v1 import History
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode


@dataclasses.dataclass
class RunHistory:
    workflow_id: str
    run_id: str
    start_time: datetime | None
    end_time: datetime | None
    history: History


def event_time(event) -> datetime:
    return event.event_time.ToDatetime(tzinfo=UTC)


def _span(history: History):
    evs = history.events
    if not evs:
        return None, None
    return event_time(evs[0]), event_time(evs[-1])


def _overlaps(s, e, win_start, win_end) -> bool:
    if e is not None and win_start is not None and e < win_start:
        return False
    if s is not None and win_end is not None and s > win_end:
        return False
    return True


def _san(wfid: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", wfid)


# Namespace divisions these system workflows run under (visibility hides them by
# default; queries must name the division to see them).
DIVISION_DEPLOYMENT = "TemporalWorkerDeployment"
DIVISION_WCI = "TemporalWorkerControllerInstance"


def _division_for(workflow_id: str) -> str:
    from .ids import WCI_PREFIX

    return DIVISION_WCI if workflow_id.startswith(WCI_PREFIX) else DIVISION_DEPLOYMENT


def _parse_history(text: str) -> History:
    h = History()
    json_format.Parse(text, h, ignore_unknown_fields=True)
    return h


class HistorySource:
    async def runs_for(self, workflow_id, win_start, win_end) -> list[RunHistory]:
        raise NotImplementedError


class LiveSource(HistorySource):
    """Dials the frontend; enumerates runs via visibility, caches each history."""

    def __init__(self, client: Client, cache_dir: str, debug: bool = False):
        self.client = client
        self.cache_dir = cache_dir
        self.debug = debug

    def _log(self, msg):
        if self.debug:
            print(f"[debug] {msg}", file=sys.stderr)

    async def runs_for(self, workflow_id, win_start, win_end) -> list[RunHistory]:
        # These system workflows run inside a namespace division, which visibility
        # hides from ordinary queries; include the division predicate so
        # list_workflows can enumerate the CAN runs. If that still comes back empty
        # (or errors), the CAN-walk fallback fetches the chain by ID directly — any
        # real connection/auth error surfaces there, not here.
        metas = []
        div = _division_for(workflow_id)
        query = f'WorkflowId = "{workflow_id}" AND TemporalNamespaceDivision = "{div}"'
        try:
            async for we in self.client.list_workflows(query=query):
                metas.append(we)
            self._log(f"list_workflows {workflow_id!r} (division {div}) -> {len(metas)} run(s)")
        except RPCError as e:
            self._log(f"list_workflows failed for {workflow_id!r} ({e.status.name}: {e.message}); using CAN-walk")
            metas = []

        if not metas:
            self._log(f"falling back to CAN-walk for {workflow_id!r}")
            return await self._can_walk(workflow_id, win_start, win_end)

        out: list[RunHistory] = []
        for we in sorted(metas, key=lambda w: (w.start_time or datetime.min.replace(tzinfo=UTC))):
            if not _overlaps(we.start_time, we.close_time, win_start, win_end):
                continue
            hist = await self._history(workflow_id, we.run_id)
            hs, he = _span(hist)
            out.append(RunHistory(workflow_id, we.run_id, hs or we.start_time, he or we.close_time, hist))
        return out

    async def _can_walk(self, workflow_id, win_start, win_end) -> list[RunHistory]:
        runs: list[RunHistory] = []
        run_id = ""  # latest
        for _ in range(10000):  # safety bound
            try:
                hist = await self._history(workflow_id, run_id)
            except RPCError as e:
                if e.status == RPCStatusCode.NOT_FOUND:
                    # Legitimately no such workflow — clean empty result.
                    self._log(f"{workflow_id!r} not found (NOT_FOUND)")
                    break
                # Connection / auth / permission / unavailable — surface loudly;
                # do not masquerade as "no history".
                raise RuntimeError(f"fetch history for {workflow_id!r} failed: {e.status.name}: {e.message}") from e
            hs, he = _span(hist)
            if _overlaps(hs, he, win_start, win_end):
                started = hist.events[0].workflow_execution_started_event_attributes
                rid = run_id or started.original_execution_run_id
                runs.append(RunHistory(workflow_id, rid, hs, he, hist))
            started = hist.events[0].workflow_execution_started_event_attributes
            prev = started.continued_execution_run_id
            # Stop once we've walked entirely before the window.
            if (
                hs is not None
                and win_start is not None
                and hs < win_start
                and not _overlaps(hs, he, win_start, win_end)
            ):
                break
            if not prev:
                break
            run_id = prev
        runs.sort(key=lambda r: (r.start_time or datetime.min.replace(tzinfo=UTC)))
        return runs

    async def _history(self, workflow_id, run_id) -> History:
        d = os.path.join(self.cache_dir, _san(workflow_id))
        os.makedirs(d, exist_ok=True)
        if run_id:
            cache = os.path.join(d, f"{run_id}_events.json")
            if os.path.exists(cache):
                try:
                    with open(cache) as fh:
                        text = fh.read()
                    if text.strip():
                        return _parse_history(text)
                except Exception as e:  # empty/corrupt cache -> re-fetch
                    self._log(f"ignoring bad cache {cache}: {e}")
        handle = self.client.get_workflow_handle(workflow_id, run_id=run_id or None)
        # fetch_history() returns a temporalio WorkflowHistory wrapper (not a proto);
        # its to_json() is the protojson we cache and re-parse into a History proto.
        raw = await handle.fetch_history()
        text = raw.to_json()
        rid = run_id or raw.run_id
        # Atomic write so a crash never leaves a partial/empty cache file behind.
        final = os.path.join(d, f"{rid}_events.json")
        tmp = os.path.join(d, f".{rid}.tmp")
        with open(tmp, "w") as fh:
            fh.write(text)
        os.replace(tmp, final)
        return _parse_history(text)


class OfflineSource(HistorySource):
    """Indexes a folder (recursively) of ``*_events.json`` protojson dumps."""

    def __init__(self, dirs: list[str]):
        self.index: dict[str, list[RunHistory]] = {}
        for d in dirs:
            for path in glob.glob(os.path.join(d, "**", "*_events.json"), recursive=True):
                with open(path) as fh:
                    hist = _parse_history(fh.read())
                if not hist.events:
                    continue
                started = hist.events[0].workflow_execution_started_event_attributes
                wfid = started.workflow_id
                run_id = started.original_execution_run_id or os.path.basename(path).replace("_events.json", "")
                hs, he = _span(hist)
                self.index.setdefault(wfid, []).append(RunHistory(wfid, run_id, hs, he, hist))
        for runs in self.index.values():
            runs.sort(key=lambda r: (r.start_time or datetime.min.replace(tzinfo=UTC)))

    async def runs_for(self, workflow_id, win_start, win_end) -> list[RunHistory]:
        return [r for r in self.index.get(workflow_id, []) if _overlaps(r.start_time, r.end_time, win_start, win_end)]


async def list_deployments(client: Client) -> list[str]:
    """Return the deployment names visible in the namespace (via the
    deployment-workflow type), newest activity first."""
    from .ids import DELIM, DEPLOYMENT_PREFIX

    prefix = DEPLOYMENT_PREFIX + DELIM
    names = {}
    query = (
        'WorkflowType = "temporal-sys-worker-deployment-workflow" '
        f'AND TemporalNamespaceDivision = "{DIVISION_DEPLOYMENT}"'
    )
    async for we in client.list_workflows(query=query):
        if we.id.startswith(prefix):
            name = we.id[len(prefix) :]
            t = we.start_time or datetime.min.replace(tzinfo=UTC)
            if name not in names or t > names[name]:
                names[name] = t
    return [n for n, _ in sorted(names.items(), key=lambda kv: kv[1], reverse=True)]
