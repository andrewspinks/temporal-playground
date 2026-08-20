#!/usr/bin/env python3
"""WCI / worker-deployment forensics.

Given a deployment and a time window, determine which versions were in play,
when each started/finished draining, and — for serverless (WCI-managed)
versions — measure worker invocations, poll cadence, and scaling metrics.

Fetch histories live (direct SDK dial: API key or mTLS, optional proxy) or
analyze a folder of pre-downloaded `*_events.json` dumps offline.

Examples:
  # Live (Temporal Cloud, API key), last 4h:
  python wci_forensics.py --deployment <deployment> \
      --namespace <namespace> --address <namespace>.tmprl.cloud:7233 \
      --api-key "$TEMPORAL_API_KEY" --start now-4h

  # Offline (folder of dumps):
  python wci_forensics.py --deployment <deployment> --offline ./dumps
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from forensics import ids
from forensics.deployment import analyze_deployment
from forensics.fetch import HistorySource, LiveSource, OfflineSource
from forensics.report import build_report
from forensics.util import cloud_url
from forensics.version import analyze_version
from forensics.wci import analyze_wci


def _log(msg):
    print(msg, file=sys.stderr)


def parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    if s.lower() == "now":
        return datetime.now(timezone.utc)
    m = re.fullmatch(r"(?:now)?-(\d+)([smhd])", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        field = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[unit]
        return datetime.now(timezone.utc) - timedelta(**{field: n})
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--deployment", help="worker deployment name")
    p.add_argument("--list-deployments", action="store_true",
                   help="list deployment names visible in the namespace, then exit (live only)")
    p.add_argument("--debug", action="store_true", help="verbose diagnostics to stderr")
    p.add_argument("--start", help="window start (RFC3339 or now-<N>[smhd])")
    p.add_argument("--end", help="window end (RFC3339 or now); default now")
    p.add_argument("--namespace", default=os.environ.get("TEMPORAL_NAMESPACE"))
    p.add_argument("--address", default=os.environ.get("TEMPORAL_ADDRESS"), help="frontend host:port")
    p.add_argument("--api-key", default=os.environ.get("TEMPORAL_API_KEY"))
    p.add_argument("--tls", action="store_true", help="force TLS (implied by --api-key)")
    p.add_argument("--no-tls", action="store_true",
                   help="force plaintext, e.g. a local gRPC proxy (overrides --api-key auto-TLS)")
    p.add_argument("--tls-cert", help="mTLS client cert (PEM)")
    p.add_argument("--tls-key", help="mTLS client key (PEM)")
    p.add_argument("--tls-ca", help="server CA cert (PEM)")
    p.add_argument("--tls-server-name", help="override TLS server name (SNI)")
    p.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY"), help="HTTP-connect proxy host:port")
    p.add_argument("--proxy-user")
    p.add_argument("--proxy-pass")
    p.add_argument("--task-queue", action="append", default=[], metavar="TQ",
                   help="extra task queue(s) to check for poller/version mismatches (repeatable, live only)")
    p.add_argument("--offline", nargs="+", metavar="DIR", help="analyze *_events.json dumps in these dirs (no dial)")
    p.add_argument("--cache-dir", help="where to cache histories + write report (default ./wci-forensics-out/<deployment>)")
    p.add_argument("--json", action="store_true", help="also print the JSON summary to stdout")
    p.add_argument("--format", choices=["auto", "terminal", "markdown"], default="auto",
                   help="stdout format (auto: terminal when a TTY, else markdown). report.md is always Markdown.")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color in terminal output")
    p.add_argument("--ui-base", default="https://cloud.temporal.io",
                   help="Temporal UI base URL for generated links")
    return p


async def _connect(a):
    if not a.address or not a.namespace:
        sys.exit("live mode needs --address and --namespace (or use --offline)")
    from forensics.connect import ConnOptions, connect

    return await connect(ConnOptions(
        address=a.address, namespace=a.namespace, api_key=a.api_key, tls=a.tls, no_tls=a.no_tls,
        tls_cert=a.tls_cert, tls_key=a.tls_key, tls_ca=a.tls_ca, tls_server_name=a.tls_server_name,
        proxy=a.proxy, proxy_user=a.proxy_user, proxy_pass=a.proxy_pass,
    ))


async def make_source(a) -> HistorySource:
    if a.offline:
        return OfflineSource(a.offline)
    return LiveSource(await _connect(a), a.cache_dir, debug=a.debug)


async def run(a) -> int:
    if a.list_deployments:
        from forensics.fetch import list_deployments

        names = await list_deployments(await _connect(a))
        print(f"Worker deployments visible in {a.namespace}:")
        for n in names:
            print(f"  {n}")
        if not names:
            print("  (none found via visibility — check namespace/credentials)")
        return 0

    if not a.deployment:
        sys.exit("--deployment is required (or use --list-deployments)")

    win_start, win_end = parse_time(a.start), parse_time(a.end)
    a.cache_dir = a.cache_dir or os.path.join("wci-forensics-out", a.deployment)
    os.makedirs(a.cache_dir, exist_ok=True)

    src = await make_source(a)
    dep = a.deployment

    def announce(label, wfid):
        _log(f"[processing] {label}: {cloud_url(a.namespace, wfid, ui_base=a.ui_base) or wfid}")

    dep_wfid = ids.deployment_wfid(dep)
    announce("deployment", dep_wfid)
    dep_runs = await src.runs_for(dep_wfid, win_start, win_end)
    if not dep_runs:
        wfid = ids.deployment_wfid(dep)
        sys.exit(
            f"no deployment-workflow history found for {dep!r} in window.\n"
            f"  looked for workflow id: {wfid}\n"
            f"  hints: verify the deployment name with --list-deployments; widen --start/--end;\n"
            f"         or re-run with --debug to see the visibility/fetch results."
        )
    dep_analysis = analyze_deployment(dep_runs, win_start, win_end)

    versions = {}
    wcis = {}
    link_groups = [("deployment", ids.deployment_wfid(dep), dep_runs)]
    for build in dep_analysis.versions_in_play:
        version_wfid = ids.version_wfid(dep, build)
        announce(f"version {build[:12]}", version_wfid)
        vruns = await src.runs_for(version_wfid, win_start, win_end)
        if not vruns:
            continue  # no version-workflow history for this build in the window/source
        va = analyze_version(build, vruns)
        versions[build] = va
        link_groups.append((f"version:{build[:8]}", version_wfid, vruns))
        if va.serverless:
            wci_wfid = ids.wci_wfid(dep, build)
            announce(f"wci {build[:12]}", wci_wfid)
            wruns = await src.runs_for(wci_wfid, win_start, win_end)
            if wruns:
                wcis[build] = analyze_wci(build, wruns, va.draining_start, va.drained_at)
                link_groups.append((f"wci:{build[:8]}", wci_wfid, wruns))

    # Live poller / version-match check (needs a frontend connection).
    poller_statuses = []
    client = getattr(src, "client", None)
    if client is not None:
        from forensics.pollers import check_task_queue

        tqs = set(a.task_queue or [])
        for v in versions.values():
            tqs.update(v.task_queues)
        tqs.add(dep)  # serverless task queue is often named after the deployment
        for tq in sorted(tqs):
            _log(f"[processing] describe task-queue pollers: {tq}")
            poller_statuses.append(await check_task_queue(client, a.namespace, tq))

    markdown, summary = build_report(
        dep, dep_analysis, versions, wcis, win_start, win_end,
        namespace=a.namespace, link_groups=link_groups, ui_base=a.ui_base,
        poller_statuses=poller_statuses, debug=a.debug,
    )

    with open(os.path.join(a.cache_dir, "report.md"), "w") as fh:
        fh.write(markdown)
    with open(os.path.join(a.cache_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    fmt = a.format
    if fmt == "auto":
        fmt = "terminal" if sys.stdout.isatty() else "markdown"
    if fmt == "terminal":
        from forensics.terminal import to_terminal

        color = (not a.no_color) and sys.stdout.isatty()
        print(to_terminal(markdown, color=color))
    else:
        print(markdown)

    if a.json:
        print("\n--- summary.json ---")
        print(json.dumps(summary, indent=2))
    print(f"\n[written to {a.cache_dir}/report.md and summary.json]", file=sys.stderr)
    return 0


def main():
    a = build_args().parse_args()
    raise SystemExit(asyncio.run(run(a)))


if __name__ == "__main__":
    main()
