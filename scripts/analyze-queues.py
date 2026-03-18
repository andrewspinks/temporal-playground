#!/usr/bin/env python3
"""Analyze task queues from captured gRPC call JSON files.

Supports multiple workers polling the same queue — breaks down poll counts
and task delivery per identity. Outputs a Markdown report to queue-analysis.md
in the captures directory, and also prints to stdout.

Uses tcp_stream (TCP connection ID) to correlate poll responses back to the
requesting worker — all polls on the same connection share a queue and identity.

Usage: python3 scripts/analyze-queues.py [captures-dir]
  Default captures-dir: captures/grpc-calls
"""

import json
import glob
import os
import sys
from collections import defaultdict


def load_json_files(captures_dir):
    """Load all numbered JSON files from the captures directory."""
    pattern = os.path.join(captures_dir, "[0-9]*.json")
    files = sorted(glob.glob(pattern))
    calls = []
    for f in files:
        with open(f) as fh:
            calls.append(json.load(fh))
    return calls


def extract_wft_detail(payload):
    """Extract what triggered this workflow task.

    Looks only at events in the window between the last WORKFLOW_TASK_COMPLETED
    and WORKFLOW_TASK_SCHEDULED. Events that are command side-effects of the
    previous WFT (e.g. TIMER_STARTED, UPDATE_ACCEPTED written after that WFT
    completed) can appear in the same window alongside the actual trigger
    (e.g. TIMER_FIRED). We collect all genuine trigger-type events in the
    window; if there is more than one it means multiple things demanded a WFT
    simultaneously and the server coalesced them into a single dispatch.

    Returns (triggers: list[str], coalesced: bool).
    """
    TRIGGER_TYPES = {
        "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED",
        "EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_REQUESTED",
        "EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_ACCEPTED",
        "EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_COMPLETED",
        "EVENT_TYPE_ACTIVITY_TASK_COMPLETED",
        "EVENT_TYPE_ACTIVITY_TASK_FAILED",
        "EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT",
        "EVENT_TYPE_TIMER_FIRED",
        "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED",
        "EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED",
        "EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_FAILED",
    }

    history = payload.get("history", {})
    events = history.get("events", [])

    # Find the window between the last WFT_COMPLETED and WFT_SCHEDULED.
    sched_idx = None
    completed_idx = None
    for i, event in enumerate(events):
        et = event.get("event_type", "")
        if et == "EVENT_TYPE_WORKFLOW_TASK_COMPLETED":
            completed_idx = i
        if et == "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED":
            sched_idx = i

    start = (completed_idx + 1) if completed_idx is not None else 0
    end = sched_idx if sched_idx is not None else len(events)
    window = events[start:end]

    triggers = []
    for event in window:
        et = event.get("event_type", "")
        if et in TRIGGER_TYPES:
            short = et.replace("EVENT_TYPE_", "").replace("_", " ").title()
            triggers.append(short)

    return triggers, len(triggers) > 1


def detect_replay(payload):
    """Detect whether a workflow task delivery requires history replay.

    A replay occurs when the server delivers the full history (starting from
    event_id 1) and there are prior WORKFLOW_TASK_COMPLETED events — the worker
    must replay through those before processing the new events. This typically
    happens when:
      - The previous worker died and a new one picks up the workflow
      - The sticky queue timed out and the task was rescheduled on the normal queue

    Returns (is_replay: bool, replay_tasks: int) where replay_tasks is the
    number of prior workflow tasks that must be replayed.
    """
    events = payload.get("history", {}).get("events", [])
    if not events:
        return False, 0
    first_eid = events[0].get("event_id", "0")
    if str(first_eid) != "1":
        return False, 0
    wft_completed = sum(
        1 for e in events
        if e.get("event_type") == "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"
    )
    return wft_completed > 0, wft_completed


def build_task(method, payload, seq):
    """Build a task detail dict from a poll response payload."""
    if method == "PollWorkflowTaskQueue":
        wf = payload.get("workflow_execution", {})
        triggers, coalesced = extract_wft_detail(payload)
        is_replay, replay_tasks = detect_replay(payload)
        return {
            "type": "Workflow",
            "seq": seq,
            "workflow_type": payload.get("workflow_type", {}).get("name", "?"),
            "workflow_id": wf.get("workflow_id", "?"),
            "run_id": wf.get("run_id", "?"),
            "attempt": payload.get("attempt", 1),
            "triggers": triggers,
            "coalesced": coalesced,
            "replay": is_replay,
            "replay_tasks": replay_tasks,
        }
    else:
        wf = payload.get("workflow_execution", {})
        return {
            "type": "Activity",
            "seq": seq,
            "activity_type": payload.get("activity_type", {}).get("name", "?"),
            "activity_id": payload.get("activity_id", "?"),
            "workflow_type": payload.get("workflow_type", {}).get("name", "?"),
            "workflow_id": wf.get("workflow_id", "?"),
            "attempt": payload.get("attempt", 1),
        }


def analyze_queues(captures_dir):
    calls = load_json_files(captures_dir)

    # Key: (namespace, queue_name, kind, normal_name)
    # Value per identity: { poll_types, poll_count, task_count, tasks: [] }
    queues = defaultdict(lambda: defaultdict(lambda: {
        "poll_types": set(),
        "poll_count": 0,
        "task_count": 0,
        "tasks": [],
    }))

    # Connection-level map: (tcp_stream, method) -> (queue_key, identity).
    # All polls on the same TCP connection share a queue and identity,
    # so we can attribute responses without matching HTTP/2 stream IDs.
    conn_queue = {}  # (tcp_stream, method) -> (queue_key, identity)

    for call in calls:
        method = call.get("method_name", "")
        direction = call.get("direction", "")
        payload = call.get("payload") or {}
        seq = call.get("seq")
        tcp = call.get("tcp_stream", "")

        if direction == "request" and method in ("PollWorkflowTaskQueue", "PollActivityTaskQueue"):
            tq = payload.get("task_queue", {})
            ns = payload.get("namespace", "?")
            name = tq.get("name", "?")
            kind = tq.get("kind", "?")
            normal = tq.get("normal_name", "")
            identity = payload.get("identity", "?")
            poll_type = "Workflow" if "Workflow" in method else "Activity"

            key = (ns, name, kind, normal)
            queues[key][identity]["poll_types"].add(poll_type)
            queues[key][identity]["poll_count"] += 1
            conn_queue[(tcp, method)] = (key, identity)

        elif direction == "response" and method in ("PollWorkflowTaskQueue", "PollActivityTaskQueue"):
            msg_len = int(call.get("grpc_message_length", "0"))
            if msg_len == 0:
                continue

            conn_key = (tcp, method)
            if conn_key in conn_queue:
                key, identity = conn_queue[conn_key]
                queues[key][identity]["task_count"] += 1
                queues[key][identity]["tasks"].append(build_task(method, payload, seq))

    # --- Collect all tasks with queue label for the unified section ---
    # Each entry: (seq, queue_label, identity, task)
    all_tasks_flat = []

    for key, identities in queues.items():
        ns, name, kind, normal = key
        kind_short = "NORMAL" if "NORMAL" in kind else "STICKY"
        queue_label = f"{name} ({kind_short})"
        for identity, info in identities.items():
            for task in info["tasks"]:
                all_tasks_flat.append((task.get("seq") or 0, queue_label, identity, task))

    all_tasks_flat.sort(key=lambda x: x[0])

    # --- Build output lines ---
    lines = []

    lines.append("# Task Queue Analysis")
    lines.append("")

    # Group by namespace
    by_ns = defaultdict(list)
    for key in sorted(queues.keys()):
        by_ns[key[0]].append(key)

    for ns in sorted(by_ns.keys()):
        lines.append(f"## Namespace: `{ns}`")
        lines.append("")

        for key in by_ns[ns]:
            _, name, kind, normal = key
            identities = queues[key]
            kind_short = "NORMAL" if "NORMAL" in kind else "STICKY"

            all_poll_types = set()
            total_polls = 0
            total_tasks = 0
            for identity, info in identities.items():
                all_poll_types |= info["poll_types"]
                total_polls += info["poll_count"]
                total_tasks += info["task_count"]

            poll_types = " + ".join(sorted(all_poll_types))
            task_status = f"**yes** ({total_tasks})" if total_tasks > 0 else "no"
            sticky_note = f" *(sticky for: {normal})*" if normal else ""

            lines.append(f"### `{name}`")
            lines.append("")
            lines.append(f"| | |")
            lines.append(f"|---|---|")
            lines.append(f"| Kind | {kind_short}{sticky_note} |")
            lines.append(f"| Poll type | {poll_types} |")
            lines.append(f"| Got tasks | {task_status} |")
            lines.append(f"| Total polls | {total_polls} |")

            if len(identities) == 1:
                identity = next(iter(identities))
                lines.append(f"| Identity | `{identity}` |")
            else:
                worker_lines = []
                for identity in sorted(identities):
                    info = identities[identity]
                    w_types = " + ".join(sorted(info["poll_types"]))
                    w_tasks = info["task_count"]
                    suffix = f", got {w_tasks} tasks" if w_tasks > 0 else ""
                    worker_lines.append(f"`{identity}` ({w_types}, {info['poll_count']} polls{suffix})")
                lines.append(f"| Workers | {'<br>'.join(worker_lines)} |")

            lines.append("")

    # --- Unified task list sorted by seq ---
    lines.append("---")
    lines.append("")
    lines.append("## All Tasks Delivered")
    lines.append("")

    if not all_tasks_flat:
        lines.append("*No tasks delivered.*")
        lines.append("")
    else:
        for _, queue_label, identity, task in all_tasks_flat:
            seq_ref = f"[{task['seq']}]" if task.get("seq") else ""

            if task["type"] == "Workflow":
                replay_badge = " REPLAY" if task.get("replay") else ""
                lines.append(f"- {seq_ref} **Workflow task{replay_badge}** — `{task['workflow_type']}` attempt {task['attempt']}")
                lines.append(f"  - Queue: `{queue_label}`")
                lines.append(f"  - Workflow: `{task['workflow_id']}`")
                lines.append(f"  - Run: `{task['run_id']}`")
                if task.get("replay"):
                    lines.append(f"  - Replay: full history delivered, replaying {task['replay_tasks']} prior workflow task(s)")
                if task.get("triggers"):
                    coalesced_note = " *(coalesced into one task)*" if task.get("coalesced") else ""
                    lines.append(f"  - Triggered by: {', '.join(task['triggers'])}{coalesced_note}")
                lines.append(f"  - Delivered to: `{identity}`")
            else:
                lines.append(f"- {seq_ref} **Activity task** — `{task['activity_type']}` (id: {task['activity_id']}) attempt {task['attempt']}")
                lines.append(f"  - Queue: `{queue_label}`")
                lines.append(f"  - Workflow: `{task['workflow_type']}` / `{task['workflow_id']}`")
                lines.append(f"  - Delivered to: `{identity}`")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    captures_dir = sys.argv[1] if len(sys.argv) > 1 else "captures/grpc-calls"
    if not os.path.isdir(captures_dir):
        print(f"Error: directory not found: {captures_dir}", file=sys.stderr)
        sys.exit(1)

    output = analyze_queues(captures_dir)

    # Write markdown file
    out_path = os.path.join(captures_dir, "queue-analysis.md")
    with open(out_path, "w") as f:
        f.write(output)

    # Also print to stdout
    print(output)
    print(f"\n→ Written to {out_path}", file=sys.stderr)
