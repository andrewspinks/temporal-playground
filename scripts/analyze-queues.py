#!/usr/bin/env python3
"""Analyze task queues from captured gRPC call JSON files.

Supports multiple workers polling the same queue — breaks down poll counts
and task delivery per identity. Outputs a Markdown report to queue-analysis.md
in the captures directory, and also prints to stdout.

Uses tcp_stream (TCP connection ID) to correlate poll responses back to the
requesting worker. For responses whose request frame was not captured (e.g.
the HTTP/2 stream was opened before the capture started), falls back to
matching by workflow_id seen in prior matched responses. Tasks that cannot
be attributed to any queue are listed in an "Unattributed Tasks" section.

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
    """Extract a summary of what triggered a workflow task."""
    history = payload.get("history", {})
    events = history.get("events", [])
    triggers = []
    for event in events:
        et = event.get("event_type", "")
        # Only include the most meaningful event types as triggers
        if et in (
            "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED",
            "EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_ACCEPTED",
            "EVENT_TYPE_WORKFLOW_EXECUTION_UPDATE_COMPLETED",
            "EVENT_TYPE_ACTIVITY_TASK_COMPLETED",
            "EVENT_TYPE_ACTIVITY_TASK_FAILED",
            "EVENT_TYPE_TIMER_FIRED",
            "EVENT_TYPE_SIGNAL_EXTERNAL_WORKFLOW_EXECUTION_INITIATED",
            "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED",
            "EVENT_TYPE_CHILD_WORKFLOW_EXECUTION_COMPLETED",
        ):
            short = et.replace("EVENT_TYPE_", "").replace("_", " ").title()
            triggers.append(short)
    return triggers


def build_task(method, payload, seq, inferred=False):
    """Build a task detail dict from a poll response payload."""
    if method == "PollWorkflowTaskQueue":
        wf = payload.get("workflow_execution", {})
        return {
            "type": "Workflow",
            "seq": seq,
            "workflow_type": payload.get("workflow_type", {}).get("name", "?"),
            "workflow_id": wf.get("workflow_id", "?"),
            "run_id": wf.get("run_id", "?"),
            "attempt": payload.get("attempt", 1),
            "triggers": extract_wft_detail(payload),
            "inferred": inferred,
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
            "inferred": inferred,
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

    # Index poll requests by (tcp_stream, stream_id) so we can match responses
    # to the requesting identity.
    poll_requests_by_stream = {}  # (tcp_stream, stream_id) -> (queue_key, identity)

    # Built from matched responses: (workflow_id, method) -> (queue_key, identity).
    # Keyed by method so WFT and activity responses don't clobber each other
    # (WFTs go to the sticky queue; activities go to the normal queue).
    # Used to attribute responses whose request frame was not captured.
    workflow_to_queue = {}

    # Non-empty responses with no matching request, deferred for fallback attribution.
    unmatched_responses = []

    for call in calls:
        method = call.get("method_name", "")
        direction = call.get("direction", "")
        payload = call.get("payload") or {}
        seq = call.get("seq")

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

            tcp = call.get("tcp_stream", "")
            sid = call.get("stream_id", "")
            poll_requests_by_stream[(tcp, sid)] = (key, identity)

        elif direction == "response" and method in ("PollWorkflowTaskQueue", "PollActivityTaskQueue"):
            msg_len = int(call.get("grpc_message_length", "0"))
            if msg_len == 0:
                continue

            tcp = call.get("tcp_stream", "")
            sid = call.get("stream_id", "")
            lookup_key = (tcp, sid)

            if lookup_key in poll_requests_by_stream:
                key, identity = poll_requests_by_stream[lookup_key]
                queues[key][identity]["task_count"] += 1
                queues[key][identity]["tasks"].append(build_task(method, payload, seq))

                # Record (workflow_id, method) → queue so unmatched responses can be attributed.
                wf_id = (payload.get("workflow_execution") or {}).get("workflow_id", "")
                if wf_id and wf_id not in ("?", ""):
                    workflow_to_queue[(wf_id, method)] = (key, identity)
            else:
                unmatched_responses.append(call)

    # --- Attribute unmatched responses via workflow_id fallback ---
    truly_unattributed = []
    for call in unmatched_responses:
        method = call.get("method_name", "")
        payload = call.get("payload") or {}
        seq = call.get("seq")
        wf_id = (payload.get("workflow_execution") or {}).get("workflow_id", "")

        if wf_id and wf_id not in ("?", "") and (wf_id, method) in workflow_to_queue:
            key, identity = workflow_to_queue[(wf_id, method)]
            queues[key][identity]["task_count"] += 1
            queues[key][identity]["tasks"].append(build_task(method, payload, seq, inferred=True))
        else:
            truly_unattributed.append(call)

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

            # Aggregate totals
            all_poll_types = set()
            total_polls = 0
            total_tasks = 0
            all_tasks = []
            for identity, info in identities.items():
                all_poll_types |= info["poll_types"]
                total_polls += info["poll_count"]
                total_tasks += info["task_count"]
                for t in info["tasks"]:
                    all_tasks.append((identity, t))

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

            # Task delivery details
            if all_tasks:
                lines.append("#### Tasks Delivered")
                lines.append("")
                for identity, task in all_tasks:
                    seq_ref = f"[{task['seq']}]" if task.get("seq") else ""
                    inferred_note = " *(attribution inferred from workflow id)*" if task.get("inferred") else ""
                    if task["type"] == "Workflow":
                        lines.append(f"- {seq_ref} **Workflow task** — `{task['workflow_type']}` attempt {task['attempt']}{inferred_note}")
                        lines.append(f"  - Workflow: `{task['workflow_id']}`")
                        lines.append(f"  - Run: `{task['run_id']}`")
                        if task["triggers"]:
                            lines.append(f"  - Triggered by: {', '.join(task['triggers'])}")
                        lines.append(f"  - Delivered to: `{identity}`")
                    else:
                        lines.append(f"- {seq_ref} **Activity task** — `{task['activity_type']}` (id: {task['activity_id']}) attempt {task['attempt']}{inferred_note}")
                        lines.append(f"  - Workflow: `{task['workflow_type']}` / `{task['workflow_id']}`")
                        lines.append(f"  - Delivered to: `{identity}`")
                    lines.append("")

    # --- Unattributed tasks (no matching request and no workflow_id match) ---
    if truly_unattributed:
        lines.append("---")
        lines.append("")
        lines.append("## Unattributed Tasks")
        lines.append("")
        lines.append(f"*{len(truly_unattributed)} task(s) whose poll request was not captured and could not be"
                     " attributed via workflow id (e.g. decode errors with no prior context).*")
        lines.append("")
        for call in truly_unattributed:
            method = call.get("method_name", "")
            payload = call.get("payload") or {}
            seq = call.get("seq")
            seq_ref = f"[{seq}]" if seq else ""
            decode_err = "_decode_error" in payload
            if decode_err:
                lines.append(f"- {seq_ref} **{method}** — payload decode error (stream not captured)")
            elif method == "PollWorkflowTaskQueue":
                wf = payload.get("workflow_execution", {})
                wf_type = payload.get("workflow_type", {}).get("name", "?")
                lines.append(f"- {seq_ref} **Workflow task** — `{wf_type}` wf=`{wf.get('workflow_id','?')}`")
            else:
                wf = payload.get("workflow_execution", {})
                act_type = payload.get("activity_type", {}).get("name", "?")
                lines.append(f"- {seq_ref} **Activity task** — `{act_type}` wf=`{wf.get('workflow_id','?')}`")
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
