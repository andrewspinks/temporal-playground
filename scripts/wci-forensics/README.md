# wci-forensics

Given a **worker deployment** and a **time window**, reconstruct what happened:

1. **Deployment workflow** → which version(s) were current/ramping and the transition times.
2. **Version workflows** → drainage start/finish per version, serverless (WCI-managed) flag,
   and `delete-version` attempts blocked by active pollers.
3. **WCI workflows** (serverless versions) → InvokeWorker (Lambda) invocation count +
   per-minute frequency, how many happened **after draining**, PullStats cadence, scaling
   metrics, and how the controller chain terminated.

Outputs a consolidated timeline (with workflow + run IDs), a drain summary, per-WCI metrics,
`summary.json`, and a cache of every raw history for offline re-analysis.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

The binary-protobuf deployment/version state is decoded via a committed descriptor set
(`descriptors/deployment_descriptors.binpb`). It only needs regenerating if the pinned
`go.temporal.io/server` / `go.temporal.io/api` versions in the
`temporal-auto-scaled-workers` repo change:

```bash
descriptors/gen_descriptors.sh   # needs Go + that repo checked out
```

## Usage

Live (Temporal Cloud, API key):
```bash
python wci_forensics.py \
  --deployment <deployment> \
  --namespace  <namespace> \
  --address    <namespace>.tmprl.cloud:7233 \
  --api-key    "$TEMPORAL_API_KEY" \
  --start 2026-01-01T00:00:00Z --end 2026-01-01T06:00:00Z
```

Live via mTLS and/or an HTTP-connect proxy:
```bash
python wci_forensics.py --deployment <dep> --namespace <ns> --address <host:7233> \
  --tls-cert client.pem --tls-key client.key \
  --proxy proxy.internal:3128 --proxy-user u --proxy-pass p \
  --start now-4h
```

```bash
python wci_forensics.py --deployment <dep> --namespace <ns> \
  --address 127.0.0.1:8080 --no-tls
```

Offline (folder of `*_events.json` dumps, no connection):
```bash
python wci_forensics.py --deployment <deployment> \
  --offline ./dumps
```

Connection flags also read env vars: `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`,
`TEMPORAL_API_KEY`, `HTTPS_PROXY`. Live runs cache each history under
`--cache-dir` (default `./wci-forensics-out/<deployment>/`), so re-runs are fast and the
raw histories can later be fed back with `--offline`.

Each **consolidated timeline** row's `run#event` column is a short clickable link
(`<run8>#<eventId>`) pointing at the exact history event that triggered it
(`…/history/events/<eventId>`) — a Markdown link, or an OSC-8 terminal hyperlink in
`--format terminal`. The exhaustive per-run **Temporal Cloud links** section (a UI URL for
every run of every workflow) is verbose and now only rendered under `--debug`; it remains in
`summary.json` either way. Links need a namespace, so pass `--namespace` even in `--offline`
mode to get them; override the UI host with `--ui-base` (default `https://cloud.temporal.io`).

Other flags:
- `--format {auto,terminal,markdown}` — stdout format. `auto` (default) prints colorized,
  aligned **terminal** output when stdout is a TTY, else Markdown. `report.md` is always
  Markdown regardless. `--no-color` disables ANSI color.
- `--task-queue TQ` (repeatable) — extra task queue(s) to check for poller/version
  mismatches (a worker polling a build id that isn't the task queue's current version gets
  no tasks). Live only; the deployment-named task queue and any version-registered queues are
  checked automatically. Mismatches are flagged in a top-of-report ⚠️ Warnings section.
- `--list-deployments` — list the deployment names visible in the namespace, then exit
  (handy when a run reports "no deployment-workflow history found").
- `--debug` — print the visibility/fetch results per workflow to stderr, and include the
  exhaustive per-run **Temporal Cloud links** section in the report.

## How it works

- Workflow IDs are rebuilt inline (`forensics/ids.py`):
  `temporal-sys-worker-deployment:<dep>`,
  `temporal-sys-worker-deployment-version:<dep>:<build>`,
  `temporal-sys-worker-controller-instance:<dep>:<build>`.
- Each workflow continues-as-new frequently; runs are enumerated via visibility
  (`WorkflowId = "…"`) with a CAN-chain walk fallback, then filtered to the window.
- Payloads: `json/plain` → dict; server-internal `binary/protobuf` (deployment/version
  state) → dynamic proto via the descriptor pool (`forensics/decode.py`).

## Test

The regression test replays a saved incident (a folder of `*_events.json` dumps) and
asserts the derived facts. It reads a local **fixture** describing the dump folder and the
expected values — no customer data is committed. Copy `tests/fixture.example.json`, fill in
your dump path / deployment / expected timings, and point the test at it. The test skips
when no fixture is present.

```bash
cp tests/fixture.example.json tests/fixture.json   # then edit tests/fixture.json
WCI_GOLDEN_FIXTURE=tests/fixture.json python tests/golden_test.py
```
