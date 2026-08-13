import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from app.constants import TARGET_ID


@workflow.defn
class TargetWorkflow:
    """The contended workflow.

    Sleeps long enough that it is still Running when the second "service" tries
    to start the same Workflow ID.
    """

    @workflow.run
    async def run(self) -> str:
        await asyncio.sleep(60)
        return "target done"


@workflow.defn
class ParentWorkflow:
    """The service that starts the same work as a CHILD workflow.

    This is the path that has no protection available. On the client,
    ``id_conflict_policy=USE_EXISTING`` makes a duplicate start return the
    already-running execution. Here there is no equivalent.
    """

    @workflow.run
    async def run(self) -> str:
        # There is no `id_conflict_policy` keyword on start_child_workflow /
        # execute_child_workflow -- passing one raises TypeError. It is not just
        # missing from the Python SDK: StartChildWorkflowExecutionCommandAttributes
        # has no workflow_id_conflict_policy field, so it cannot be expressed on
        # the wire at all. See temporalio/temporal#6799 and temporalio/features#558.
        #
        # `id_reuse_policy` is the only related lever a child workflow gets, and it
        # governs reuse of a CLOSED execution's ID -- it cannot say "give me the
        # running one". Its TERMINATE_IF_RUNNING value does touch a running
        # execution, but it kills it rather than reusing it, so it is not a
        # USE_EXISTING substitute.
        return await workflow.execute_child_workflow(
            TargetWorkflow.run,
            id=TARGET_ID,
            # Bound the demo so a stuck child cannot hang the run.
            execution_timeout=timedelta(minutes=2),
        )
