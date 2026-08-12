# `sideEffect` + `getVersion` replay-ordering NDE

Reproduces a non-determinism error seen in production on **Java SDK 1.33.0**, and shows the same code
running clean on **1.36.1**:

```
[TMPRL1100] Event 12 of type EVENT_TYPE_ACTIVITY_TASK_SCHEDULED does not match
            command type COMMAND_TYPE_UPSERT_WORKFLOW_SEARCH_ATTRIBUTES
```

Two concurrent workflow branches wake in the same workflow task. One calls `Workflow.sideEffect`, the
other calls `Workflow.getVersion` twice. On SDK &lt; 1.34.0 the commands they emit come out in one order
while executing and a different order while replaying, so the workflow task fails and the execution is
stuck forever.

## Run

Needs a Temporal server on `localhost:7233` — `just server` from the playground root, or a
docker-compose stack. Override with `TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE`.

Requires SA to be created:

```
temporal operator search-attribute create --name CustomKeywordField --type Keyword
```

Running with v1.33 causes NDE:

```
./gradlew -q run -PsdkVersion=1.33.0
```

Running with v1.36.1 runs cleanly

```
./gradlew -q run -PsdkVersion=1.36.1
```


## How the reproducer works

The worker sets `stickyQueueScheduleToStartTimeout = Duration.ZERO`, so every workflow task arrives as
a **full replay** of history. That is the condition that exposes the bug: with a warm sticky cache the
commands are matched in the order they were emitted and the run is green — which is why this looks
intermittent in production and surfaces after a rollout, an eviction or a worker restart.

The starter waits for the first workflow task to complete (so the signal lands in its own task rather
than being folded into the first one), signals, then polls history until it sees either the
non-determinism failure or a clean completion. It has to wait: the signal only *schedules* a workflow
task, and the worker must run that one plus the next one — the replay that fails — before shutting
down.

## Why it happens

- **`Workflow.sideEffect` resumes its thread at different times in the two modes.** While executing,
  the callback fires when the marker *command* is flushed. While replaying, it fires only when the
  marker *event* is matched, after the event loop has drained
  ([`SideEffectStateMachine`](https://github.com/temporalio/sdk-java/blob/master/temporal-sdk/src/main/java/io/temporal/internal/statemachines/SideEffectStateMachine.java)
  lines 56-58 vs 63/72). This asymmetry is unchanged in every SDK version to date.
- **Pre-1.34.0 `Workflow.getVersion` yields**, and on replay its callback fires *early*, from the
  preloaded marker. So during replay the deadline branch runs ahead while the acknowledge branch is
  still parked inside `sideEffect`, and emits its commands first.
- [**PR #2819**](https://github.com/temporalio/sdk-java/pull/2819) (released in **1.34.0**) changed the
  `SKIP_YIELD_ON_VERSION` gate in `SyncWorkflowContext.getVersion` from `checkSdkFlag` to
  `tryUseSdkFlag`, so new executions adopt the flag, `getVersion` stops yielding, and the branches can
  no longer interleave. Related: [#2821](https://github.com/temporalio/sdk-java/pull/2821)
  (`VERSION_WAIT_FOR_MARKER`, 1.36.0, not on by default) and
  [#2936](https://github.com/temporalio/sdk-java/pull/2936) (don't drop flags already in history when
  server capability detection fails) — which is why 1.36.1 is the version to deploy, not 1.34.0.

Command order in the workflow task that handles the signal, on 1.33.0 — the `SideEffect` marker lands
between the two `Version` markers, so the branches were running in lockstep:

```
Version(deadline-branch), SideEffect, Version(deadline-search-attribute),
ActivityTaskScheduled(Acknowledge), UpsertWorkflowSearchAttributes, ActivityTaskScheduled(NotifyDeadline)
```

On 1.36.1 each branch emits its commands contiguously and replay agrees:

```
Version(deadline-branch), Version(deadline-search-attribute), UpsertWorkflowSearchAttributes,
ActivityTaskScheduled(NotifyDeadline), SideEffect, ActivityTaskScheduled(Acknowledge)
```

