#!/usr/bin/env python3
"""Generate a Mermaid sequence diagram from captured gRPC call JSON files.

Collapses repetitive polling into notes and shows only meaningful interactions.
Supports multiple workers — each unique identity becomes its own participant.
Uses tcp_stream (TCP connection ID) to correlate identity-less calls (like
GetSystemInfo) with the worker/starter that owns that connection.

Usage: python3 scripts/sequence-diagram.py [captures-dir] [--raw]
  Default captures-dir: captures/grpc-calls
  --raw: include all polling (no simplification)
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


def generate_diagram(captures_dir, raw_mode=False):
    summary_calls = load_summary(captures_dir)
    details = load_json_files(captures_dir)
    seq_role, seq_identity = classify_calls(summary_calls, details)
    # Only use activation markers (+/-) in raw mode. In simplified mode,
    # collapsed polls and missing responses make balanced activations
    # impossible — causing Mermaid rendering errors.
    use_activations = raw_mode

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
                into_lines.append(f"    Note over {pid},Server: {' + '.join(parts)} (long-poll, waiting)")
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
        label = f"[{seq}] {method}: {annotation}" if annotation else f"[{seq}] {method}"
        label = label.replace('"', "'")

        act = "+" if use_activations else ""
        deact = "-" if use_activations else ""

        if direction == "request":
            body_lines.append(f"    {pid}->>{act}Server: {label}")
        elif direction == "response":
            if is_poll and msg_len > 0:
                if not raw_mode and pid in pending_polls and pending_polls[pid].get(method, 0) > 0:
                    pending_polls[pid][method] -= 1
                    flush_polls(body_lines, pid)
                task_type = "workflow task" if "Workflow" in method else "activity task"
                replay_note = " REPLAY" if "Workflow" in method and detect_replay(detail) else ""
                body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {method} ({task_type} delivered{replay_note})")
            elif is_poll:
                if raw_mode:
                    body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {method} (empty)")
            else:
                body_lines.append(f"    Server-->>{deact}{pid}: [{seq}] {method}")

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


if __name__ == "__main__":
    raw_mode = "--raw" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    captures_dir = args[0] if args else "captures/grpc-calls"

    if not os.path.isdir(captures_dir):
        print(f"Error: directory not found: {captures_dir}", file=sys.stderr)
        sys.exit(1)

    diagram = generate_diagram(captures_dir, raw_mode=raw_mode)

    suffix = "-raw" if raw_mode else ""
    out_path = os.path.join(captures_dir, f"sequence{suffix}.md")
    with open(out_path, "w") as f:
        f.write("```mermaid\n")
        f.write(diagram)
        f.write("\n```\n")

    print(diagram)
    print(f"\n→ Written to {out_path}", file=sys.stderr)
