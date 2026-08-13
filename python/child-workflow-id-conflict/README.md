# Workflow ID Conflict Policy does not exist for child workflows

Two services start work under the same Workflow ID at the same time. Both believe
`WorkflowIDConflictPolicy = USE_EXISTING` protects them. It protects the one that starts via the
**client**. It does nothing for the one that starts a **child workflow**, because that policy has no
representation on a child workflow start at all.

This sample walks the happy path straight into that failure and prints exactly what each layer
records.

## The gap

| | `Client.start_workflow` | `workflow.start_child_workflow` |
|---|---|---|
| `id_reuse_policy` | yes | yes |
| `id_conflict_policy` | **yes** | **no** |
| wire field | `StartWorkflowExecutionRequest.workflow_id_conflict_policy` | `StartChildWorkflowExecutionCommandAttributes` has **no such field** |

This is not a Python SDK omission — the Command has nowhere to put the policy, so no SDK can send
it. Upstream: server support [temporalio/temporal#6799](https://github.com/temporalio/temporal/issues/6799)
is open with no linked PR, and the SDK umbrella
[temporalio/features#558](https://github.com/temporalio/features/issues/558) is blocked behind it.

`id_reuse_policy` is not a substitute. It governs reuse of a **closed** execution's ID. Its
`TERMINATE_IF_RUNNING` value does reach a running execution, but it *kills* it rather than returning
it — the opposite of what a caller asking for `USE_EXISTING` wants.

## Run it

Start the dev server from the playground root (`just server`), then:

```sh
just worker    # terminal 1
just start     # terminal 2
```

`just start` is re-runnable: it terminates the contended workflow on the way out.

## What it does

1. **Service A** starts `TargetWorkflow` under `contended-workflow-id` via the client with
   `id_conflict_policy=USE_EXISTING`, twice. Both calls return the *same* run ID — deduplication
   works.
2. **Service B** starts `ParentWorkflow`, which calls `execute_child_workflow` for the same
   `contended-workflow-id`. There is no conflict policy to pass. The child start fails and the
   parent fails with it.
3. The script then prints the parent's history and final status.

## Observed output

```
STEP 1-2  Two client starts, same Workflow ID, USE_EXISTING
  service A start #1: started ok, run_id=019ff9b0-e143-7df6-8849-ea7668291b99
  service A start #2: started ok, run_id=019ff9b0-e143-7df6-8849-ea7668291b99
  -> same run id: True

STEP 3  A parent workflow starts the SAME id as a CHILD workflow
  parent FAILED, as expected:
    outer exception : WorkflowFailureError
    cause class     : FailureError
    cause message   : Workflow execution already started

STEP 4  What the parent's history actually recorded
  event 6: EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_FAILED
    workflow_id : contended-workflow-id
    cause       : START_CHILD_WORKFLOW_EXECUTION_FAILED_CAUSE_WORKFLOW_ALREADY_EXISTS
  WorkflowTaskFailed events: 0
  parent final status: FAILED
```

## Why this is invisible to `temporal_request_failure`

The parent's full history:

```
  1  WORKFLOW_EXECUTION_STARTED
  2  WORKFLOW_TASK_SCHEDULED
  3  WORKFLOW_TASK_STARTED
  4  WORKFLOW_TASK_COMPLETED                  <-- the RPC carrying the child-start Command SUCCEEDED
  5  START_CHILD_WORKFLOW_EXECUTION_INITIATED
  6  START_CHILD_WORKFLOW_EXECUTION_FAILED    <-- the failure arrives here, as an EVENT
  7  WORKFLOW_TASK_SCHEDULED
  8  WORKFLOW_TASK_STARTED
  9  WORKFLOW_TASK_COMPLETED
 10  WORKFLOW_EXECUTION_FAILED
```

A child workflow start is a **Command inside `RespondWorkflowTaskCompleted`**, not a gRPC call. That
RPC succeeds (event 4). The conflict is reported later as history event 6. No request-level metric
can observe it, which is why searching `temporal_request_failure` operations finds nothing. There is
also no `temporal_child_workflow_*` metric in any SDK
([SDK metrics reference](https://docs.temporal.io/references/sdk-metrics)).

What *is* observable, and what is not:

- **`WorkflowTaskFailed` count is 0.** The parent genuinely fails; it does not sit in a
  workflow-task retry loop. So `temporal_workflow_failed` does increment once — but that metric
  carries no failure-type tag, so it is indistinguishable from any other workflow failure.
- **The serialized failure carries no type.** In-workflow the SDK raises
  `temporalio.exceptions.WorkflowAlreadyStartedError` (`worker/_workflow_instance.py:910-922`) —
  note, *not* `ChildWorkflowError`, which only covers a child that started and then failed. But that
  class matches none of the `isinstance` branches in the failure converter's `to_failure`
  (`converter/_failure_converter.py:150+`), so **no `application_failure_info` is written**. The
  `WorkflowExecutionFailed` event holds only `message: "Workflow execution already started"` and a
  stack trace, and the client rehydrates it as a bare `FailureError`. There is no structured
  `type` field to alert on — only the literal message string.
- **The one precise signal is the history event**: `StartChildWorkflowExecutionFailed` with cause
  `WORKFLOW_ALREADY_EXISTS`.

## Files

| File | Purpose |
|---|---|
| `app/workflows.py` | `TargetWorkflow` (the contended ID) and `ParentWorkflow` (starts it as a child) |
| `app/starter.py` | The scripted sequence: client dedupe, then the child-start failure, then history |
| `app/worker.py` | One worker hosting both workflows |
| `app/constants.py` | Task queue and the fixed Workflow IDs |
| `app/shared.py` | envconfig-based `connect()` — same pattern as the other Python projects here |

## Cloud

`app/shared.py` uses `ClientConfig.load_client_connect_config()`, so `TEMPORAL_ADDRESS`,
`TEMPORAL_NAMESPACE`, and `TEMPORAL_API_KEY` (or mTLS) point this at Temporal Cloud with no code
changes.
