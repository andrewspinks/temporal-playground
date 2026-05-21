from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.service import MyInput, MyOutput


# Long-running handler workflow for testing reset behavior while the nexus operation is in progress.
# Send the 'complete' signal to unblock and return the result.
@workflow.defn
class SayHelloWorkflow:
    def __init__(self) -> None:
        self._complete = False

    @workflow.signal
    async def complete(self) -> None:
        self._complete = True

    @workflow.run
    async def run(self, input: MyInput) -> MyOutput:
        await workflow.wait_condition(lambda: self._complete)
        return MyOutput(message=f"Hello {input.name} from workflow run operation!")
