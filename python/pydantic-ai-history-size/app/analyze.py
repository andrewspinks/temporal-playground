"""Quantify event-history bloat.

Works on the JSON dict form of a history — either an exported history file
(``{"events": [...]}`` from ``just history-export`` ) or a
history fetched live by ``app/starter.py`` and converted with
``google.protobuf.json_format.MessageToDict`` (same camelCase shape, bytes as
base64), so one code path serves both.

Run standalone:  ``python -m app.analyze <history.json>``
"""

from __future__ import annotations

import base64
import json
import sys
from collections import Counter, defaultdict

SCHEDULED = "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED"


def _payload_bytes(payloads: list[dict]) -> int:
    """Total decoded byte size of a list of Temporal payloads."""
    total = 0
    for p in payloads or []:
        data = p.get("data")
        if data:
            total += len(base64.b64decode(data))
    return total


def _activity_name(event: dict) -> str:
    attrs = event.get("activityTaskScheduledEventAttributes", {})
    return attrs.get("activityType", {}).get("name", "")


def _scheduled_input_bytes(event: dict) -> int:
    attrs = event.get("activityTaskScheduledEventAttributes", {})
    return _payload_bytes(attrs.get("input", {}).get("payloads", []))


def _bar(value: int, peak: int, width: int = 40) -> str:
    filled = 0 if peak == 0 else round(width * value / peak)
    return "█" * filled + "·" * (width - filled)


def analyze_events(events: list[dict]) -> None:
    total = sum(len(json.dumps(e)) for e in events)

    counts: Counter[str] = Counter()
    bytes_by_type: dict[str, int] = defaultdict(int)
    for e in events:
        t = e.get("eventType", "?")
        counts[t] += 1
        bytes_by_type[t] += len(json.dumps(e))

    print(f"\n{'=' * 62}\nEVENT HISTORY ANALYSIS\n{'=' * 62}")
    print(f"total events : {len(events)}")
    print(f"total size   : {total:,} bytes ({total / 1024 / 1024:.2f} MB)")

    print("\n--- bytes by event type (share of total) ---")
    for t, b in sorted(bytes_by_type.items(), key=lambda x: -x[1]):
        pct = 100 * b / total if total else 0
        print(f"  {b:>11,}  {pct:5.1f}%  x{counts[t]:<3}  {t}")

    # The signature of the problem: model_request activity INPUTS (the full
    # re-sent conversation) growing turn over turn. Fall back to all scheduled
    # activity inputs if this history has no model_request activities.
    curve = [
        (int(e.get("eventId", 0)), _activity_name(e), _scheduled_input_bytes(e))
        for e in events
        if e.get("eventType") == SCHEDULED
    ]
    model_reqs = [c for c in curve if "model_request" in c[1]]
    shown, label = (model_reqs, "model_request") if model_reqs else (curve, "activity")

    if shown:
        peak = max(b for _, _, b in shown)
        first, last = shown[0][2], shown[-1][2]
        print(f"\n--- {label} activity INPUT growth (re-sent each turn) ---")
        for eid, _, b in shown:
            print(f"  event {eid:>4}  {b:>9,} B  {_bar(b, peak)}")
        grow = f"{last / first:.1f}x" if first else "n/a"
        print(
            f"\n  {len(shown)} turns · first={first:,} B · last={last:,} B · growth={grow}"
        )
        print(
            "  Each turn re-sends the whole conversation as the activity input, so\n"
            "  these payloads (stored in ACTIVITY_TASK_SCHEDULED events) dominate history."
        )
    print("=" * 62)


def analyze_file(path: str) -> None:
    with open(path) as f:
        data = json.load(f)
    events = data["events"] if isinstance(data, dict) else data
    print(f"analyzing {path}")
    analyze_events(events)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m app.analyze <history.json>", file=sys.stderr)
        raise SystemExit(2)
    analyze_file(sys.argv[1])
