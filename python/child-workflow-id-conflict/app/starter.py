import asyncio

from temporalio.api.enums.v1 import EventType, StartChildWorkflowExecutionFailedCause
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.service import RPCError, RPCStatusCode

from app.constants import PARENT_ID, TARGET_ID, TASK_QUEUE
from app.shared import connect
from app.workflows import ParentWorkflow, TargetWorkflow


def header(text: str) -> None:
    print(f"\n{'=' * 74}\n{text}\n{'=' * 74}", flush=True)


async def start_via_client(client: Client, label: str) -> str | None:
    """A 'service' starting TARGET_ID directly, asking for USE_EXISTING."""
    handle = await client.start_workflow(
        TargetWorkflow.run,
        id=TARGET_ID,
        task_queue=TASK_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )
    run_id = handle.first_execution_run_id
    print(f"  {label}: started ok, run_id={run_id}", flush=True)
    return run_id


async def main() -> None:
    client = await connect("starter")

    header("STEP 1-2  Two client starts, same Workflow ID, USE_EXISTING")
    print("  Client API exposes id_conflict_policy, so the duplicate is deduped.")
    first = await start_via_client(client, "service A start #1")
    second = await start_via_client(client, "service A start #2")
    print(f"  -> same run id: {first == second}", flush=True)

    header("STEP 3  A parent workflow starts the SAME id as a CHILD workflow")
    print("  Child workflow options have no id_conflict_policy to set.")
    parent = await client.start_workflow(
        ParentWorkflow.run,
        id=PARENT_ID,
        task_queue=TASK_QUEUE,
    )
    print(f"  parent started: {PARENT_ID} run_id={parent.first_execution_run_id}")
    try:
        result = await parent.result()
        print(f"  !! parent unexpectedly succeeded: {result!r}", flush=True)
    except WorkflowFailureError as err:
        cause = err.cause
        print("  parent FAILED, as expected:")
        print(f"    outer exception : {type(err).__name__}")
        print(f"    cause class     : {type(cause).__name__}")
        print(f"    cause message   : {cause}")
        # After crossing the server boundary the in-workflow
        # WorkflowAlreadyStartedError is rebuilt by the failure converter; print
        # whatever `type` field survived, since that is what you would alert on.
        failure_type = getattr(cause, "type", None)
        if failure_type is not None:
            print(f"    failure type    : {failure_type}")

    # header("STEP 4  What the parent's history actually recorded")
    # history = await parent.fetch_history()
    # task_failed = 0
    # for event in history.events:
    #     if event.HasField("start_child_workflow_execution_failed_event_attributes"):
    #         attrs = event.start_child_workflow_execution_failed_event_attributes
    #         print(f"  event {event.event_id}: {EventType.Name(event.event_type)}")
    #         print(f"    workflow_id : {attrs.workflow_id}")
    #         print(f"    cause       : {StartChildWorkflowExecutionFailedCause.Name(attrs.cause)}")
    #     elif event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED:
    #         task_failed += 1
    # print(f"  WorkflowTaskFailed events: {task_failed}")
    # print("  (0 means the parent genuinely failed rather than retrying the task,")
    # print("   which is what makes temporal_workflow_failed the only metric signal.)")
    # final = await client.get_workflow_handle(PARENT_ID).describe()
    # print(f"  parent final status: {final.status.name}", flush=True)

    # header("CLEANUP  Terminate the contended workflow so this is re-runnable")
    # try:
    #     await client.get_workflow_handle(TARGET_ID).terminate(reason="demo over")
    #     print(f"  terminated {TARGET_ID}", flush=True)
    # except RPCError as err:
    #     if err.status != RPCStatusCode.NOT_FOUND:
    #         raise
    #     print(f"  {TARGET_ID} was not running", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
