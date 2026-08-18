# nde-query-command-ordering

Investigating a production nondeterminism error on TypeScript SDK **1.16.1**:

```
[TMPRL1100] Nondeterminism error: Activity machine does not handle this event:
HistoryEvent(id: 1398, SignalExternalWorkflowExecutionInitiated)
```

Three `providerQueue` entity workflows became permanently unreplayable and were terminated. The
divergence is pure **command ordering**: on replay the SDK emits `scheduleActivity` where history
recorded `signalExternalWorkflowExecution`. Same build and SDK version before and after — not a
deploy.

## Reconstruction vs. instrumentation

| File                | What it is                                                                                                                                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/workflows.ts`  | **Reconstruction.** The customer's workflow, inferred from the histories. Signal/query/activity names are the real ones; the code shape is a guess that matches the observed command patterns. |
| `src/activities.ts` | **Reconstruction.** No-op `emitProviderQueueMetrics`.                                                                                                                                          |
| `src/tracer.ts`     | **Instrumentation.** Interceptor that prints the command list of every activation.                                                                                                             |
| `src/shared.ts`     | Connection config + the `tracing()` helper that wires the tracer into a Worker.                                                                                                                |
| `src/worker.ts`     | Worker (`pnpm start`).                                                                                                                                                                         |
| `src/starter.ts`    | Starts just the two workflows with fixed IDs, then prints the CLI commands, so you can drive signals and the query by hand (`pnpm starter`).                                                   |
| `src/client.ts`     | The automated experiment (`pnpm workflow`).                                                                                                                                                    |
| `src/replay.ts`     | Replay one saved history with the tracer on (`pnpm replay <file>`).                                                                                                                            |

**Nothing in the histories implies the customer uses interceptors or sinks** — their workflow tasks
record `langUsedFlags: [2]` only, meaning no interceptor-related SDK flag was ever queried. The
tracer is ours, purely so we can read command order directly instead of inferring it from event JSON.
It lives in its own module and is registered separately via
`interceptors: { workflowModules: [require.resolve('./tracer')] }`, so it never mixes into the
reconstruction.

Two deviations inside `workflows.ts` are marked `TEST ONLY` in the source: `stopSignal` (production
entity workflows run forever) and `TestKnobs.handlerHops` (the experimental lever, below).

## Names

| Identifier                     | Kind     | Wire name                   |
| ------------------------------ | -------- | --------------------------- |
| `providerQueueWorkflow`        | workflow | —                           |
| `connectionWorkflow`           | workflow | — (target of `execute_job`) |
| `publishToProviderQueueSignal` | signal   | `publish_to_provider_queue` |
| `executeJobSignal`             | signal   | `execute_job`               |
| `stopSignal`                   | signal   | `stop` (TEST ONLY)          |
| `providerQueueJobsQuery`       | query    | `provider_queue_jobs`       |
| `emitProviderQueueMetrics`     | activity | —                           |

## Run

```sh
just server                       # from the playground root
pnpm install
WORKER_ID=1 pnpm start            # terminal 2 (run 2-3 of these to model a worker fleet)
pnpm workflow                     # terminal 3 -- the automated experiment
```

The client runs in three phases: start one `connectionWorkflow`; run `ATTEMPTS` independent trials
that each burst signals at a fresh `providerQueueWorkflow` while a query storm runs; then replay
every captured history against the same code.

Knobs: `QUERIES=on|off`, `JOBS`, `ATTEMPTS`, `QUERIERS`, `HANDLER_HOPS`, `CACHE`, `WORKER_ID`.

### Driving it by hand

`pnpm starter` starts just the two workflows with fixed IDs (`provider-queue-demo`,
`connection-demo`) and prints ready-to-paste CLI commands. With the worker running, one
`publish_to_provider_queue` signal traces `commands=AS`.

To get several signals into **one** Workflow Task — the precondition for the bug — nothing must be
polling while you send them:

```sh
# 1. worker stopped
PROVIDER_QUEUE_ID=demo-1 CONNECTION_ID=conn-1 pnpm starter
# 2. send a few signals (still no worker)
for i in 1 2 3 4 5; do
  temporal workflow signal --address 127.0.0.1:7233 --workflow-id demo-1 \
    --name publish_to_provider_queue --input "\"job-$i\""
done
# 3. now start the worker
pnpm start
```

The trace shows the whole batch in one activation:

```
activate replaying=false jobs=[initializeWorkflow, signalWorkflow x5]
  commands=AAAAAS
```

Repeat with `HANDLER_HOPS=2` and fresh IDs and the same batch becomes `ASAAAA`.

> The address is passed explicitly on purpose. If anything else is bound to `:7233` over IPv6 (a
> Temporal in Docker, for instance), `localhost` can resolve to a different server for the SDK than
> for the CLI, which shows up as spurious `workflow not found` errors.

## The mechanism

Two independent coroutines push commands into the same Workflow Task:

- each `publish_to_provider_queue` handler schedules one activity → `scheduleActivity` (**A**)
- the dispatcher, parked on `condition()`, signals a connection → `signalExternalWorkflow` (**S**)

Neither pushes its command inline — both travel through async interceptor chains — so commands are
emitted during the microtask drain when the SDK exits the workflow VM.

`HANDLER_HOPS` inserts N `await`s in the signal handler before it schedules its activity. With a
12-signal Workflow Task:

| `HANDLER_HOPS` | commands emitted |
| -------------- | ---------------- |
| 1              | `AAAAAAAAAAAAS`  |
| 2              | `ASAAAAAAAAAAA`  |
| 3              | `SAAAAAAAAAAAA`  |

**One extra microtask hop walks S across the entire batch.** S's position is a pure function of the
relative microtask depth of the two coroutines — nothing else. `HANDLER_HOPS=2` reproduces
production's exact shape (`ASA`, history `b6fd434d` ev 1720).

That is also why this is an ordering bug rather than a missing-command bug, and why it only ever bit
multi-signal Workflow Tasks: with one signal there is a single A, so there is nothing for S to be
misordered against. In the real histories every corrupted task was multi-signal and every
single-signal task was fine.

## What this does NOT yet reproduce

The NDE itself. Across ~150 trials — queries on and off, 1 and 3 workers, `CACHE=0` and default,
bursts up to 12 signals, `HANDLER_HOPS` 0–3 — **every captured history replayed clean**. Wherever S
landed, it landed there identically on replay.

So a query storm alone does not perturb the ordering in this shape. That matches the SDK source: by
the time a query activation runs, the previous activation has already drained its microtasks
(`tryUnblockConditionsAndMicrotasks` loops until quiescent), so there is normally nothing left for
the query's VM exit to advance.

### The untested cell

The strongest signal in the real histories is that **3 of 3 corrupted Workflow Tasks ran on a worker
that had just rebuilt the workflow from history**, while 6 of 6 multi-signal tasks on a warm worker
were fine. This repro has not hit _cold rebuild **and** multi-signal batch_ together:

- `CACHE=0` makes every task a cold rebuild, but also makes queries slow, which serialises the burst
  — so batches never form.
- Default cache gives big batches but the workflow stays warm.

Next step: keep the worker fast but apply cache pressure (a modest `maxCachedWorkflows` with many
concurrent workflows) so eviction happens _between_ bursts.

## Open questions for the customer

The reconstruction is inferred from command patterns, not their code. The `HANDLER_HOPS` result shows
the answers change the outcome materially:

1. Where is `execute_job` emitted from — a `condition()` dispatcher loop, the `job_completed`
   handler, or a `void`ed async helper?
2. Is the `publish_to_provider_queue` handler `async`, and is the metrics activity awaited or
   fire-and-forget? **How many `await`s run before it schedules the activity is precisely what sets
   S's position.**
3. The `provider_queue_jobs` query handler body — sync snapshot, or `async`?
4. Any custom interceptors? Every interceptor adds yield points, and `SdkFlags` 3–6 exist only to
   patch NDEs caused by interceptor yield points changing.
5. Worker `maxCachedWorkflows` / `reuseV8Context` / pod count.
6. A pre-Aug-7 history containing a multi-signal Workflow Task — if those always show S last, that
   confirms the queries changed recorded command order, with no repro needed.
