# nde-query-command-ordering

Investigating a production nondeterminism error on TypeScript SDK **1.16.1**:

```
[TMPRL1100] Nondeterminism error: Activity machine does not handle this event:
HistoryEvent(id: 1398, SignalExternalWorkflowExecutionInitiated)
```

Three `providerQueue` entity workflows became permanently unreplayable and were terminated. The
divergence is pure **command ordering**: on replay the SDK emits `scheduleActivity` where history
recorded `signalExternalWorkflowExecution`. Same build and SDK version before and after — not a deploy.

## Port vs. instrumentation

| File                | What it is                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------- |
| `src/workflows.ts`  | **Port** of the customer's real source (`playground/ts/customer-nde/workflow-source/self-contained-copy.ts`). |
| `src/activities.ts` | **Port.** No-op `emitProviderQueueMetrics` with the real signature.                                           |
| `src/tracer.ts`     | **Instrumentation.** Prints the command list of every activation.                                             |
| `src/shared.ts`     | Connection config + the `tracing()` helper.                                                                   |
| `src/worker.ts`     | Worker (`pnpm start`).                                                                                        |
| `src/starter.ts`    | Starts just the two workflows with fixed IDs and prints CLI commands (`pnpm starter`).                        |
| `src/client.ts`     | The automated experiment (`pnpm workflow`).                                                                   |
| `src/replay.ts`     | Replay one saved history with the tracer on (`pnpm replay <file>`).                                           |
| `analyze.py`        | Reads worker logs and reports Workflow Tasks delivered as more than one activation.                           |

The customer runs **no interceptors and no sinks** (their worker options confirm it, and their
histories record `langUsedFlags: [2]` only). The tracer is ours; it lives in its own module and is
registered via `interceptors: { workflowModules: [...] }`. Note the customer ships a prebuilt
`workflowBundle`, for which that option is ignored — our `workflowsPath` setup is a deliberate
deviation that makes the tracer possible.

Deliberately not ported: `log.info` calls, the `continueAsNew` tail, luxon, activity timeouts other
than `startToCloseTimeout`, and the AES payload codec (it runs outside the workflow VM, so it cannot
reorder in-VM command pushes).

## The mechanism

Three command sources feed one Workflow Task:

- each `publish_to_provider_queue` handler schedules a metrics activity → `scheduleActivity` (**A**)
- each `job_completed` / `job_failed` handler does the same, **if the jobId was running** (**A**)
- the dispatcher, parked on `condition()`, signals an entity workflow → `signalExternalWorkflow`
  (**S**), then schedules a metrics activity of its own (**A**)

`proxyActivities` → `scheduleActivity` → `scheduleActivityNextHandler` pushes the command
**synchronously at call time**, and there are no interceptors to add a yield point. So within one
activation every handler's `A` is pushed during the synchronous job loop, and `S` can only follow in
the microtask drain. **`S` is necessarily last.** Confirmed here:

```
activate wf=... hl=... replaying=false jobs=[initializeWorkflow, signalWorkflow x12]
  commands=<setPatchMarker>AAAAAAAAAAAAS
```

### So how did production record `S` mid-batch?

A Workflow Task's recorded commands are the concatenation of **every activation completion** for that
task. If the signal batch is split across two activations, the dispatcher's `S` lands at the end of
the first chunk. That reproduces all three corrupted tasks exactly:

| History            | activation 1                   | activation 2         | = recorded  |
| ------------------ | ------------------------------ | -------------------- | ----------- |
| `3502a8d8` ev 1393 | 4 signals → `AAAA` + `S`       | 2 signals → `AA`     | `AAAASAA`   |
| `95f6d662` ev 760  | `job_completed`+1 → `AA` + `S` | 6 signals → `AAAAAA` | `AASAAAAAA` |
| `b6fd434d` ev 1720 | 1 signal → `A` + `S`           | 1 signal → `A`       | `ASA`       |

Independent confirmation: in `3502a8d8` the metrics activities at events **150 and 151 are
byte-identical ciphertext**. The real code explains it — `runningJobs.push(jobId)` runs _after_
`await handle.signal(...)` resolves, i.e. in a later Workflow Task, so `runningJobsCount` is unchanged
across the whole task while `enqueuedJobsCount` goes `4 → (dispatch shifts to 3) → 4` again.

Replay delivers that task as **one** activation → `AAAAAAS` → mismatch at the `S` position.

**The open question is now precise: what made the live run deliver one Workflow Task as two
activations, when replay delivers one?**

## Run

```sh
temporal server start-dev --port 7234        # or use your own server
export TEMPORAL_ADDRESS=127.0.0.1:7234
pnpm install
WORKER_ID=1 pnpm start                       # run 2+ to model the customer's multi-pod fleet
pnpm workflow                                # the automated experiment
python3 analyze.py worker1.log worker2.log   # hunt for split Workflow Tasks
```

Knobs: `QUERIES=on|off`, `JOBS`, `ATTEMPTS`, `QUERIERS`, `MAX_CONCURRENT`, `CACHE`, `WORKER_ID`,
`TEMPORAL_ADDRESS`.

`pnpm starter` starts the two workflows with fixed IDs so you can drive signals and the query by hand;
it prints ready-to-paste CLI commands and the batching recipe.

## Status

The port reproduces production's command vocabulary — `AS` dominant, plus `S`-only and `A`-only tasks
from the dispatcher's post-dispatch metrics activity, and `<setPatchMarker>` on the first patched task.

It does **not** yet reproduce the NDE. Across runs with queries on and off, 2 workers, and bursts up to
12 signals, `analyze.py` reports **zero** Workflow Tasks delivered as more than one activation, and
every captured history replays clean.

Next levers, in order:

1. Cache pressure. The customer's `entity-queue` is shared with many other workflow types at high
   volume, so their providerQueue workflows are evicted and rebuilt far more often than ours are.
   All three corrupted tasks ran on a worker that had just rebuilt from history.
2. Query timing. Queries ride on Workflow Tasks and never appear in history; a query arriving
   mid-task is the most plausible cause of a second activation.
3. Scale — production hit this ~3 times across thousands of bursts per day.
