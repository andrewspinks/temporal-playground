#!/usr/bin/env python3
"""Regression test: replay a saved incident (offline dumps) and assert the
derived facts.

Reads a local fixture (JSON) describing the dump folder, the deployment, the two
build ids, and the expected values — so no incident-specific data lives in this
repo. See tests/fixture.example.json for the schema. The test SKIPS when no
fixture is available.

Fixture location (first match): $WCI_GOLDEN_FIXTURE, argv[1], or tests/fixture.json.

  cp tests/fixture.example.json tests/fixture.json   # then edit it
  WCI_GOLDEN_FIXTURE=tests/fixture.json python tests/golden_test.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forensics import ids  # noqa: E402
from forensics.deployment import analyze_deployment  # noqa: E402
from forensics.fetch import OfflineSource  # noqa: E402
from forensics.report import build_report  # noqa: E402
from forensics.version import analyze_version  # noqa: E402
from forensics.wci import analyze_wci  # noqa: E402

HERE = os.path.dirname(__file__)


def _fixture_path():
    return (
        os.environ.get("WCI_GOLDEN_FIXTURE")
        or (sys.argv[1] if len(sys.argv) > 1 else None)
        or os.path.join(HERE, "fixture.json")
    )


def _load_fixture():
    p = _fixture_path()
    if not p or not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def _run(fx):
    dep, old, new = fx["deployment"], fx["versions"]["old"], fx["versions"]["new"]
    src = OfflineSource(fx["dumps"])

    async def go():
        dep_runs = await src.runs_for(ids.deployment_wfid(dep), None, None)
        dep_a = analyze_deployment(dep_runs)
        versions, wcis = {}, {}
        for build in (old, new):
            vruns = await src.runs_for(ids.version_wfid(dep, build), None, None)
            va = analyze_version(build, vruns)
            versions[build] = va
            wruns = await src.runs_for(ids.wci_wfid(dep, build), None, None)
            if wruns:
                wcis[build] = analyze_wci(build, wruns, va.draining_start, va.drained_at)
        _, summary = build_report(dep, dep_a, versions, wcis, None, None)
        return summary

    return asyncio.run(go())


def _actuals(summary, old, new):
    into_old = [t for t in summary["transitions"] if t["to"] == old]
    into_new = [t for t in summary["transitions"] if t["to"] == new]
    v = summary["versions"].get(old, {})
    w = (summary["wci"].get(old) or {}).get("invoke", {})
    term = (summary["wci"].get(old) or {}).get("terminal") or ""

    def hms(s):
        return (s or "")[11:19] or None

    def ms(s):
        return (s or "")[11:23] or None

    return {
        "transition_into_old_hms": into_old[0]["at"][11:19] if into_old else None,
        "transition_into_new_hms": into_new[0]["at"][11:19] if into_new else None,
        "transition_into_new_from": into_new[0]["from"] if into_new else None,
        "old_serverless": v.get("serverless"),
        "old_draining_start": ms(v.get("draining_start")),
        "old_drained": ms(v.get("drained_at")),
        "old_deleted": ms(v.get("deleted_at")),
        "old_delete_blocked": v.get("delete_blocked_by_pollers"),
        "delete_block_times": [b["at"][11:19] for b in summary["delete_blocks"] if b["build"] == old],
        "invoke_total": w.get("total"),
        "invoke_failed": w.get("failed"),
        "invoke_last_hms": hms(w.get("last")),
        "invoke_peak_per_min": w.get("peak_per_min"),
        "invokes_after_draining_start": w.get("after_draining_start"),
        "invokes_after_drained": w.get("after_drained"),
        "_terminal": term,
    }


def _check(fx):
    summary = _run(fx)
    actual = _actuals(summary, fx["versions"]["old"], fx["versions"]["new"])
    checks = []
    for key, want in fx["expected"].items():
        if key == "terminal_contains":
            got = actual["_terminal"]
            checks.append((key, str(want).lower() in got.lower(), got))
        else:
            got = actual.get(key)
            checks.append((key, got == want, f"{got!r} (want {want!r})"))
    return checks


def test_golden():
    fx = _load_fixture()
    if not fx:
        try:
            import pytest

            pytest.skip("no fixture (set WCI_GOLDEN_FIXTURE or create tests/fixture.json)")
        except ImportError:
            return
    failed = [c for c in _check(fx) if not c[1]]
    assert not failed, "\n".join(f"  FAIL {name}: {detail}" for name, _, detail in failed)


def main():
    fx = _load_fixture()
    if not fx:
        print(f"SKIP: no fixture at {_fixture_path()} (copy tests/fixture.example.json).")
        return 0
    ok = True
    for name, passed, detail in _check(fx):
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed
    print("\nGOLDEN:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
