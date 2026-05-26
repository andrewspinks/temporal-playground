from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import NexusOperationError

with workflow.unsafe.imports_passed_through():
    from app.service import MyInput, SayHelloService, MyOutput

NEXUS_ENDPOINT = "hello-nexus-basic-nexus-endpoint"


# This is a workflow that calls two nexus operations.
@workflow.defn
class CallerWorkflow:
    # An __init__ method is always optional on a workflow class. Here we use it to set the
    # nexus client, but that could alternatively be done in the run method.
    def __init__(self):
        self.nexus_client = workflow.create_nexus_client(
            service=SayHelloService,
            endpoint=NEXUS_ENDPOINT,
        )

    # The workflow run method invokes two nexus operations.
    @workflow.run
    async def run(self, name: str) -> tuple[MyOutput, MyOutput]:
        # Start the nexus operation and wait for the result in one go, using execute_operation.
        op_1_result = await self.nexus_client.execute_operation(
            SayHelloService.my_sync_operation,
            MyInput(name=name),
        )
        # Alternatively, you can use start_operation to obtain the operation handle and
        # then `await` the handle to obtain the result.
        op_2_handle = await self.nexus_client.start_operation(
            SayHelloService.say_hello,
            MyInput(name=name),
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        try:
            op_2_result = await op_2_handle
        except NexusOperationError as e:
            # Non-retryable: arrives immediately after the handler workflow fails.
            # Retryable: arrives after schedule_to_close_timeout is exceeded.
            workflow.logger.error(
                "Nexus async operation failed",
                extra={"operation": e.operation, "service": e.service, "cause": str(e.cause)},
            )
            return op_1_result, MyOutput(message=f"[FAILED] {e.operation}: {e.cause}")
        return op_1_result, op_2_result

        # return op_2_result
