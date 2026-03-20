#!/usr/bin/env python3
"""Generate a Mermaid sequence diagram from captured gRPC call JSON files.

Collapses repetitive polling into notes and shows only meaningful interactions.
Supports multiple workers — each unique identity becomes its own participant.
Uses tcp_stream (TCP connection ID) to correlate identity-less calls (like
GetSystemInfo) with the worker/starter that owns that connection.

Usage: python3 scripts/sequence-diagram.py [captures-dir] [--raw] [--services]
  Default captures-dir: captures/grpc-calls
  --raw: include all polling (no simplification)
  --services: show internal service routing (Frontend→History/Matching/Visibility)
"""

import json
import glob
import os
import sys
from collections import defaultdict, OrderedDict


def load_summary(captures_dir):
    """Load calls from summary.json."""
    summary_path = os.path.join(captures_dir, "summary.json")
    with open(summary_path) as fh:
        return json.load(fh)["calls"]


def load_json_files(captures_dir):
    """Load individual JSON files for payload details."""
    pattern = os.path.join(captures_dir, "[0-9]*.json")
    files = sorted(glob.glob(pattern))
    by_seq = {}
    for f in files:
        with open(f) as fh:
            data = json.load(fh)
            by_seq[data["seq"]] = data
    return by_seq


# API priority mappings from temporal/service/frontend/configs/quotas.go
# Keys are short method names (without the full gRPC service path).
# Prefix: E = Execution, V = Visibility, NR = NamespaceReplication
API_PRIORITY = {
    # Execution P0: System
    "GetClusterInfo": "E0", "GetSystemInfo": "E0", "GetSearchAttributes": "E0",
    "DescribeNamespace": "E0", "ListNamespaces": "E0", "DeprecateNamespace": "E0",
    # Execution P1: External events + progress (completions/heartbeats)
    "SignalWorkflowExecution": "E1", "SignalWithStartWorkflowExecution": "E1",
    "StartWorkflowExecution": "E1", "UpdateWorkflowExecution": "E1",
    "ExecuteMultiOperation": "E1", "CreateSchedule": "E1",
    "StartBatchOperation": "E1", "StartActivityExecution": "E1",
    "RecordActivityTaskHeartbeat": "E1", "RecordActivityTaskHeartbeatById": "E1",
    "RespondActivityTaskCompleted": "E1", "RespondActivityTaskCompletedById": "E1",
    "RespondWorkflowTaskCompleted": "E1", "RespondQueryTaskCompleted": "E1",
    "RespondNexusTaskCompleted": "E1",
    # Execution P2: State changes
    "RequestCancelWorkflowExecution": "E2", "TerminateWorkflowExecution": "E2",
    "ResetWorkflowExecution": "E2", "DeleteWorkflowExecution": "E2",
    "GetWorkflowExecutionHistory": "E2", "UpdateSchedule": "E2",
    "PatchSchedule": "E2", "DeleteSchedule": "E2", "StopBatchOperation": "E2",
    "UpdateActivityOptions": "E2", "PauseActivity": "E2", "UnpauseActivity": "E2",
    "ResetActivity": "E2", "UpdateWorkflowExecutionOptions": "E2",
    "SetCurrentDeployment": "E2", "SetCurrentDeploymentVersion": "E2",
    "SetWorkerDeploymentCurrentVersion": "E2", "SetWorkerDeploymentRampingVersion": "E2",
    "SetWorkerDeploymentManager": "E2", "DeleteWorkerDeployment": "E2",
    "DeleteWorkerDeploymentVersion": "E2", "UpdateWorkerDeploymentVersionMetadata": "E2",
    "CreateWorkflowRule": "E2", "DescribeWorkflowRule": "E2",
    "DeleteWorkflowRule": "E2", "ListWorkflowRules": "E2", "TriggerWorkflowRule": "E2",
    "UpdateTaskQueueConfig": "E2", "RequestCancelActivityExecution": "E2",
    "TerminateActivityExecution": "E2", "DeleteActivityExecution": "E2",
    "PauseWorkflowExecution": "E2", "UnpauseWorkflowExecution": "E2",
    # Execution P3: Status queries + failure/cancel responses
    "DescribeWorkflowExecution": "E3", "DescribeActivityExecution": "E3",
    "DescribeTaskQueue": "E3", "GetWorkerBuildIdCompatibility": "E3",
    "GetWorkerVersioningRules": "E3", "ListTaskQueuePartitions": "E3",
    "QueryWorkflow": "E3", "DescribeSchedule": "E3", "ListScheduleMatchingTimes": "E3",
    "DescribeBatchOperation": "E3", "DescribeDeployment": "E3",
    "GetCurrentDeployment": "E3", "DescribeWorkerDeploymentVersion": "E3",
    "DescribeWorkerDeployment": "E3",
    "RespondActivityTaskCanceled": "E3", "RespondActivityTaskCanceledById": "E3",
    "RespondActivityTaskFailed": "E3", "RespondActivityTaskFailedById": "E3",
    "RespondWorkflowTaskFailed": "E3", "RespondNexusTaskFailed": "E3",
    # Execution P4: Polls + low priority
    "PollActivityExecution": "E4", "PollWorkflowTaskQueue": "E4",
    "PollActivityTaskQueue": "E4", "PollWorkflowExecutionUpdate": "E4",
    "PollNexusTaskQueue": "E4", "ResetStickyTaskQueue": "E4",
    "ShutdownWorker": "E4", "GetWorkflowExecutionHistoryReverse": "E4",
    "RecordWorkerHeartbeat": "E4", "FetchWorkerConfig": "E4", "UpdateWorkerConfig": "E4",
    # Execution P5: Long-poll variants + OpenAPI
    "PollWorkflowExecutionHistory": "E5", "PollActivityExecutionDescription": "E5",
    # Visibility (separate rate limiter)
    "CountWorkflowExecutions": "V1", "ScanWorkflowExecutions": "V1",
    "ListOpenWorkflowExecutions": "V1", "ListClosedWorkflowExecutions": "V1",
    "ListWorkflowExecutions": "V1", "ListArchivedWorkflowExecutions": "V1",
    "ListWorkers": "V1", "DescribeWorker": "V1",
    "CountActivityExecutions": "V1", "ListActivityExecutions": "V1",
    "GetWorkerTaskReachability": "V1", "ListSchedules": "V1", "CountSchedules": "V1",
    "ListBatchOperations": "V1", "ListDeployments": "V1",
    "GetDeploymentReachability": "V1", "ListWorkerDeployments": "V1",
    # Namespace replication inducing (separate rate limiter)
    "RegisterNamespace": "NR1", "UpdateNamespace": "NR1",
    "UpdateWorkerBuildIdCompatibility": "NR2", "UpdateWorkerVersioningRules": "NR2",
}

# Static routing map: which backend service(s) each gRPC method is forwarded to
# by the Frontend service. Derived from temporal/service/frontend/workflow_handler.go.
# "Frontend" means the call is handled entirely by the Frontend service.
METHOD_SERVICE_ROUTING = {
    # Frontend-only (no backend hop)
    "GetSystemInfo": ["Frontend"],
    "GetClusterInfo": ["Frontend"],
    "DescribeNamespace": ["Frontend"],
    "ListNamespaces": ["Frontend"],
    "RegisterNamespace": ["Frontend"],
    "UpdateNamespace": ["Frontend"],
    "DeprecateNamespace": ["Frontend"],
    "GetSearchAttributes": ["Frontend"],
    # Frontend → History
    "SignalWorkflowExecution": ["History"],
    "TerminateWorkflowExecution": ["History"],
    "RequestCancelWorkflowExecution": ["History"],
    "ResetWorkflowExecution": ["History"],
    "DeleteWorkflowExecution": ["History"],
    "GetWorkflowExecutionHistory": ["History"],
    "GetWorkflowExecutionHistoryReverse": ["History"],
    "DescribeWorkflowExecution": ["History"],
    "QueryWorkflow": ["History"],
    "UpdateWorkflowExecution": ["History"],
    "PollWorkflowExecutionUpdate": ["History"],
    "RecordActivityTaskHeartbeat": ["History"],
    "RecordActivityTaskHeartbeatById": ["History"],
    "RespondActivityTaskCompleted": ["History"],
    "RespondActivityTaskCompletedById": ["History"],
    "RespondActivityTaskFailed": ["History"],
    "RespondActivityTaskFailedById": ["History"],
    "RespondActivityTaskCanceled": ["History"],
    "RespondActivityTaskCanceledById": ["History"],
    "RespondWorkflowTaskFailed": ["History"],
    "ResetStickyTaskQueue": ["History"],
    "PauseWorkflowExecution": ["History"],
    "UnpauseWorkflowExecution": ["History"],
    "UpdateWorkflowExecutionOptions": ["History"],
    "UpdateActivityOptions": ["History"],
    "PauseActivity": ["History"],
    "UnpauseActivity": ["History"],
    "ResetActivity": ["History"],
    # Frontend → History + Matching (creates workflow/commands, then enqueues tasks)
    "StartWorkflowExecution": ["History", "Matching"],
    "SignalWithStartWorkflowExecution": ["History", "Matching"],
    "ExecuteMultiOperation": ["History", "Matching"],
    "RespondWorkflowTaskCompleted": ["History", "Matching"],
    # Frontend → Matching
    "PollWorkflowTaskQueue": ["Matching"],
    "PollActivityTaskQueue": ["Matching"],
    "RespondQueryTaskCompleted": ["Matching"],
    "ListTaskQueuePartitions": ["Matching"],
    "DescribeTaskQueue": ["Matching"],
    "RespondNexusTaskCompleted": ["Matching"],
    "RespondNexusTaskFailed": ["Matching"],
    "PollNexusTaskQueue": ["Matching"],
    "UpdateTaskQueueConfig": ["Matching"],
    # Frontend → Visibility
    "ListWorkflowExecutions": ["Visibility"],
    "CountWorkflowExecutions": ["Visibility"],
    "ScanWorkflowExecutions": ["Visibility"],
    "ListOpenWorkflowExecutions": ["Visibility"],
    "ListClosedWorkflowExecutions": ["Visibility"],
    "ListArchivedWorkflowExecutions": ["Visibility"],
    "ListSchedules": ["Visibility"],
    "CountSchedules": ["Visibility"],
    "ListBatchOperations": ["Visibility"],
    "ListDeployments": ["Visibility"],
    "GetDeploymentReachability": ["Visibility"],
    "ListWorkerDeployments": ["Visibility"],
    "ListWorkers": ["Visibility"],
    "DescribeWorker": ["Visibility"],
    "CountActivityExecutions": ["Visibility"],
    "ListActivityExecutions": ["Visibility"],
    "GetWorkerTaskReachability": ["Visibility"],
    # Frontend → History (schedule/batch operations are history-managed)
    "CreateSchedule": ["History"],
    "UpdateSchedule": ["History"],
    "PatchSchedule": ["History"],
    "DeleteSchedule": ["History"],
    "DescribeSchedule": ["History"],
    "ListScheduleMatchingTimes": ["History"],
    "StartBatchOperation": ["History"],
    "StopBatchOperation": ["History"],
    "DescribeBatchOperation": ["History"],
}


def get_service_routing(method):
    """Return the list of backend services a method routes to, or ['Frontend']."""
    return METHOD_SERVICE_ROUTING.get(method, ["Frontend"])


def get_priority_tag(method):
    """Return a priority annotation like '[E1]' for the method, or ''."""
    pri = API_PRIORITY.get(method, "")
    return f"[{pri}]" if pri else ""


def extract_detail(method, detail):
    """Extract a short annotation from the payload."""
    payload = (detail or {}).get("payload") or {}

    if method == "StartWorkflowExecution":
        wf_type = payload.get("workflow_type", {}).get("name", "")
        wf_id = payload.get("workflow_id", "")
        return f"{wf_type} ({wf_id[:20]}...)" if len(wf_id) > 20 else f"{wf_type} ({wf_id})"

    if method == "UpdateWorkflowExecution":
        req = payload.get("request", {})
        inp = req.get("input", {})
        name = inp.get("name", "")
        return f"update: {name}" if name else ""

    if method == "RespondWorkflowTaskCompleted":
        commands = payload.get("commands", [])
        cmd_types = [c.get("command_type", "").replace("COMMAND_TYPE_", "") for c in commands]
        return ", ".join(cmd_types) if cmd_types else ""

    if method == "RespondActivityTaskFailed":
        failure = payload.get("failure", {})
        return failure.get("message", "")[:50]

    return ""


def detect_replay(detail):
    """Check if a workflow task delivery is a replay."""
    payload = (detail or {}).get("payload") or {}
    events = payload.get("history", {}).get("events", [])
    if not events or str(events[0].get("event_id", "0")) != "1":
        return False
    return any(e.get("event_type") == "EVENT_TYPE_WORKFLOW_TASK_COMPLETED" for e in events)


def make_participant_id(name):
    """Turn a string into a safe Mermaid participant ID."""
    return "".join(c if c.isalnum() else "_" for c in name)


def extract_identity(payload):
    """Extract identity from payload, handling nested locations."""
    if not payload:
        return ""
    ident = payload.get("identity", "")
    if ident:
        return ident
    # Nested in request.meta.identity (UpdateWorkflowExecution)
    req = payload.get("request", {})
    meta = req.get("meta", {})
    return meta.get("identity", "")


def classify_calls(summary_calls, details):
    """Classify every call into a role ('starter', 'worker', 'system') and
    assign an identity string. Returns (seq_role, seq_identity) dicts.

    Uses tcp_stream to group calls by TCP connection. All calls on the same
    connection share an identity and role, so we build connection-level maps
    first and then resolve each call from its connection.
    """

    STARTER_METHODS = {
        "StartWorkflowExecution", "UpdateWorkflowExecution",
        "GetWorkflowExecutionHistory",
    }

    # Build connection-level maps: identity and role for each TCP connection
    conn_identity = {}  # tcp_stream -> identity (first seen)
    conn_role = {}      # tcp_stream -> "system" | "starter" | "worker"

    for seq in sorted(details.keys()):
        d = details[seq]
        tcp = d.get("tcp_stream", "")
        if not tcp:
            continue
        payload = (d.get("payload") or {})
        identity = extract_identity(payload)
        method_name = d.get("method_name", "")
        ns = payload.get("namespace", "")

        if identity and tcp not in conn_identity:
            conn_identity[tcp] = identity

        if tcp not in conn_role:
            conn_role[tcp] = "worker"
        if ns == "temporal-system":
            conn_role[tcp] = "system"
        elif method_name in STARTER_METHODS and conn_role[tcp] != "system":
            conn_role[tcp] = "starter"

    # Classify each call using connection-level maps
    seq_role = {}
    seq_identity = {}

    for call in summary_calls:
        seq = call["seq"]
        detail = details.get(seq, {})
        method = call["method"]
        tcp = detail.get("tcp_stream", "")

        # Identity: prefer payload, fall back to connection
        payload = (detail.get("payload") or {})
        identity = extract_identity(payload) or conn_identity.get(tcp, "")

        # Role: prefer specific signals, fall back to connection
        ns = payload.get("namespace", "")
        if ns == "temporal-system":
            role = "system"
        elif method in STARTER_METHODS:
            role = "starter"
        else:
            role = conn_role.get(tcp, "worker")

        seq_role[seq] = role
        seq_identity[seq] = identity or role

    return seq_role, seq_identity


def generate_diagram(captures_dir, raw_mode=False, services_mode=False):
    summary_calls = load_summary(captures_dir)
    details = load_json_files(captures_dir)
    seq_role, seq_identity = classify_calls(summary_calls, details)
    # Only use activation markers (+/-) in raw mode. In simplified mode,
    # collapsed polls and missing responses make balanced activations
    # impossible — causing Mermaid rendering errors.
    use_activations = raw_mode
    # Track which backend services are actually used (for participant declarations)
    used_services = set()

    # Build participant list in order of first appearance
    seen_participants = OrderedDict()
    for call in summary_calls:
        seq = call["seq"]
        role = seq_role.get(seq, "worker")
        if role == "system":
            continue
        identity = seq_identity.get(seq, "?")
        part_key = (role, identity)
        if part_key not in seen_participants:
            seen_participants[part_key] = True

    # Assign display names — disambiguate only when multiple participants
    # share the same role
    by_role = defaultdict(list)
    for role, identity in seen_participants:
        by_role[role].append(identity)

    participant_display = {}
    participant_id = {}

    for role, identities in by_role.items():
        base = "Starter" if role == "starter" else "Worker"

        if len(identities) == 1:
            key = (role, identities[0])
            participant_display[key] = base
            participant_id[key] = base
        else:
            short_names = []
            for ident in identities:
                short = ident.split("@")[0] if "@" in ident else ident
                if len(short) > 20:
                    short = short[:17] + "..."
                short_names.append(short)

            if len(set(short_names)) < len(short_names):
                for i, ident in enumerate(identities):
                    key = (role, ident)
                    name = f"{base}{i + 1}"
                    participant_display[key] = name
                    participant_id[key] = name
            else:
                for ident, short in zip(identities, short_names):
                    key = (role, ident)
                    display = f"{base} ({short})"
                    safe_id = f"{base}_{make_participant_id(short)}"
                    participant_display[key] = display
                    participant_id[key] = safe_id

    def get_pid(seq):
        role = seq_role.get(seq, "worker")
        identity = seq_identity.get(seq, "?")
        return participant_id.get((role, identity), "Worker")

    # --- Generate body lines first, then declare only used participants ---
    body_lines = []
    pending_polls = defaultdict(lambda: defaultdict(int))

    def flush_polls(into_lines, specific_pid=None):
        pids_to_flush = [specific_pid] if specific_pid else list(pending_polls.keys())
        for pid in list(pids_to_flush):
            if pid not in pending_polls:
                continue
            counts = pending_polls[pid]
            parts = []
            if counts.get("PollWorkflowTaskQueue", 0) > 0:
                parts.append(f"{counts['PollWorkflowTaskQueue']}x PollWorkflowTaskQueue")
            if counts.get("PollActivityTaskQueue", 0) > 0:
                parts.append(f"{counts['PollActivityTaskQueue']}x PollActivityTaskQueue")
            if parts:
                server_name = "Frontend" if services_mode else "Server"
                into_lines.append(f"    Note over {pid},{server_name}: {' + '.join(parts)} (long-poll, waiting)")
            del pending_polls[pid]

    for call in summary_calls:
        seq = call["seq"]
        method = call["method"]
        direction = call["direction"]
        msg_len = int(call.get("msg_len", "0"))
        detail = details.get(seq)
        role = seq_role.get(seq, "worker")

        if role == "system":
            continue

        pid = get_pid(seq)
        is_poll = method in ("PollWorkflowTaskQueue", "PollActivityTaskQueue")

        if not raw_mode and is_poll and direction == "request":
            pending_polls[pid][method] += 1
            continue

        if not raw_mode and is_poll and direction == "response" and msg_len == 0:
            continue

        # Flush pending polls before non-poll events for this participant
        if not raw_mode and not is_poll and pid in pending_polls:
            flush_polls(body_lines, pid)

        annotation = extract_detail(method, detail) if detail else ""
        pri = get_priority_tag(method)
        label_parts = [f"[{seq}]", pri, method]
        label_base = " ".join(p for p in label_parts if p)
        label = f"{label_base}: {annotation}" if annotation else label_base
        label = label.replace('"', "'")

        act = "+" if use_activations else ""
        deact = "-" if use_activations else ""

        if services_mode:
            routing = get_service_routing(method)
            frontend_only = routing == ["Frontend"]
            for svc in routing:
                used_services.add(svc)
            if not frontend_only:
                used_services.add("Frontend")

            if direction == "request":
                body_lines.append(f"    {pid}->>{act}Frontend: {label}")
                if not frontend_only:
                    for svc in routing:
                        if svc != "Frontend":
                            body_lines.append(f"    Frontend->>{svc}: routes to {svc}")
            elif direction == "response":
                if is_poll and msg_len > 0:
                    if not raw_mode and pid in pending_polls and pending_polls[pid].get(method, 0) > 0:
                        pending_polls[pid][method] -= 1
                        flush_polls(body_lines, pid)
                    task_type = "workflow task" if "Workflow" in method else "activity task"
                    replay_note = " REPLAY" if "Workflow" in method and detect_replay(detail) else ""
                    body_lines.append(f"    Frontend-->>{deact}{pid}: [{seq}] {pri} {method} ({task_type} delivered{replay_note})")
                elif is_poll:
                    if raw_mode:
                        body_lines.append(f"    Frontend-->>{deact}{pid}: [{seq}] {pri} {method} (empty)")
                else:
                    body_lines.append(f"    Frontend-->>{deact}{pid}: [{seq}] {pri} {method}")
        else:
            if direction == "request":
                body_lines.append(f"    {pid}->>{act}Server: {label}")
            elif direction == "response":
                if is_poll and msg_len > 0:
                    if not raw_mode and pid in pending_polls and pending_polls[pid].get(method, 0) > 0:
                        pending_polls[pid][method] -= 1
                        flush_polls(body_lines, pid)
                    task_type = "workflow task" if "Workflow" in method else "activity task"
                    replay_note = " REPLAY" if "Workflow" in method and detect_replay(detail) else ""
                    body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {pri} {method} ({task_type} delivered{replay_note})")
                elif is_poll:
                    if raw_mode:
                        body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {pri} {method} (empty)")
                else:
                    body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {pri} {method}")

    if not raw_mode:
        flush_polls(body_lines)

    # Determine which participants actually appear in the body
    body_text = "\n".join(body_lines)
    used_pids = set()
    for key, pid in participant_id.items():
        if pid in body_text:
            used_pids.add(pid)

    # Build final output with header + only used participants
    lines = ["sequenceDiagram"]

    starters = [(k, v) for k, v in participant_id.items() if k[0] == "starter" and v in used_pids]
    workers = [(k, v) for k, v in participant_id.items() if k[0] == "worker" and v in used_pids]

    for key, pid in starters:
        display = participant_display[key]
        if display == pid:
            lines.append(f"    participant {pid}")
        else:
            lines.append(f"    participant {pid} as {display}")

    if services_mode:
        # Declare service participants in architectural order, only if used
        lines.append("    participant Frontend")
        for svc in ["History", "Matching", "Visibility"]:
            if svc in used_services:
                lines.append(f"    participant {svc}")
    else:
        lines.append("    participant Server")

    for key, pid in workers:
        display = participant_display[key]
        if display == pid:
            lines.append(f"    participant {pid}")
        else:
            lines.append(f"    participant {pid} as {display}")
    lines.append("")
    lines.extend(body_lines)

    return "\n".join(lines)


# Descriptions for each priority tag, grouped by rate limiter pool.
PRIORITY_KEY = OrderedDict([
    ("E0", "System (GetClusterInfo, GetSystemInfo, ...)"),
    ("E1", "External events + completions (Start, Signal, Respond*Completed, Heartbeat)"),
    ("E2", "State changes (Cancel, Terminate, Reset, Delete, GetHistory, Schedules)"),
    ("E3", "Status queries + failure responses (Describe*, Query, Respond*Failed)"),
    ("E4", "Polls + low priority (Poll*TaskQueue, ResetStickyTaskQueue, ShutdownWorker)"),
    ("E5", "Long-poll variants (GetHistory w/ WaitNewEvent, DescribeActivity w/ LongPollToken)"),
    ("V1", "Visibility (List*, Count*, Scan*)"),
    ("NR1", "Namespace replication P1 (RegisterNamespace, UpdateNamespace)"),
    ("NR2", "Namespace replication P2 (UpdateWorkerBuildIdCompatibility, UpdateWorkerVersioningRules)"),
])


def generate_priority_key(diagram_text):
    """Return a markdown priority key containing only tags that appear in the diagram."""
    lines = ["## Priority Key", ""]
    lines.append("| Tag | Rate Limiter | Description |")
    lines.append("|-----|-------------|-------------|")
    for tag, desc in PRIORITY_KEY.items():
        if f"[{tag}]" in diagram_text:
            pool = {"E": "Execution", "V": "Visibility", "N": "Namespace Replication"}[tag[0]]
            lines.append(f"| `{tag}` | {pool} | {desc} |")
    lines.append("")
    return "\n".join(lines)


SERVICE_DESCRIPTIONS = OrderedDict([
    ("Frontend", "gRPC gateway — auth, rate limiting, namespace ops"),
    ("History", "Workflow state machine, event history, command processing"),
    ("Matching", "Task queue dispatch, polling, task delivery"),
    ("Visibility", "Search and list queries (backed by Elasticsearch/SQL)"),
])


def generate_service_key(diagram_text):
    """Return a markdown service routing key for services that appear in the diagram."""
    present = [svc for svc in SERVICE_DESCRIPTIONS if svc in diagram_text]
    if not present:
        return ""
    lines = ["## Service Routing", ""]
    lines.append("All SDK traffic enters via Frontend. Arrows like `Frontend->>History` show internal routing.")
    lines.append("")
    lines.append("| Service | Description |")
    lines.append("|---------|-------------|")
    for svc in present:
        lines.append(f"| **{svc}** | {SERVICE_DESCRIPTIONS[svc]} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raw_mode = "--raw" in sys.argv
    services_mode = "--services" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    captures_dir = args[0] if args else "captures/grpc-calls"

    if not os.path.isdir(captures_dir):
        print(f"Error: directory not found: {captures_dir}", file=sys.stderr)
        sys.exit(1)

    diagram = generate_diagram(captures_dir, raw_mode=raw_mode, services_mode=services_mode)
    priority_key = generate_priority_key(diagram)
    service_key = generate_service_key(diagram) if services_mode else ""

    suffix = "-raw" if raw_mode else ""
    if services_mode:
        suffix += "-services"
    out_path = os.path.join(captures_dir, f"sequence{suffix}.md")
    with open(out_path, "w") as f:
        f.write(priority_key)
        if service_key:
            f.write(service_key)
        f.write("```mermaid\n")
        f.write(diagram)
        f.write("\n```\n")

    print(priority_key)
    if service_key:
        print(service_key)
    print(diagram)
    print(f"\n→ Written to {out_path}", file=sys.stderr)
