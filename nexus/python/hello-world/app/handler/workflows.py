from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.service import MyInput, MyOutput


# Long-running handler workflow for testing reset behavior while the nexus operation is in progress.
# Send the 'complete' signal to unblock and return the result.
# Special names trigger error paths for observing Nexus error handling behavior:
#   "fail-now"  → non-retryable ApplicationError (immediate failure, no retries)
#   "retry-me"  → retryable ApplicationError (workflow retries until caller times out)
@workflow.defn
class SayHelloWorkflow:
    def __init__(self) -> None:
        self._complete = False

    @workflow.signal
    async def complete(self) -> None:
        self._complete = True

    @workflow.run
    async def run(self, input: MyInput) -> MyOutput:
        if input.name == "fail-now":
            # Non-retryable: caller sees NexusOperationStarted then NexusOperationFailed immediately.
            raise ApplicationError("simulated non-retryable failure", non_retryable=True)
        if input.name == "retry-me":
            if workflow.info().attempt < 3:
                # Fails on attempts 1 and 2.
                raise ApplicationError(f"simulated transient failure (attempt {workflow.info().attempt})")
            # Succeeds on attempt 3 — return immediately without waiting for signal.
            return MyOutput(message=f"Hello {input.name} — succeeded on attempt {workflow.info().attempt}!")
        await workflow.wait_condition(lambda: self._complete)
        return MyOutput(message=f"Hello {input.name} from workflow run operation!")
