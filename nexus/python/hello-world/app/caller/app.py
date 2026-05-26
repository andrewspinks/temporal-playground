import asyncio
import sys
import uuid
from typing import Optional

from temporalio.client import Client
from temporalio.envconfig import ClientConfig
from temporalio.worker import Worker

from app.caller.workflows import CallerWorkflow
from app.service import MyOutput

NAMESPACE = "hello-nexus-basic-caller-namespace"
TASK_QUEUE = "hello-nexus-basic-caller-task-queue"


async def execute_caller_workflow(
    client: Optional[Client] = None,
    name: str = "world",
) -> tuple[MyOutput, MyOutput]:
    if not client:
        config = ClientConfig.load_client_connect_config()
        # Override the namespace from config file.
        config.setdefault("target_host", "localhost:7233")
        config.setdefault("namespace", NAMESPACE)
        client = await Client.connect(**config)

    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CallerWorkflow],
    ):
        return await client.execute_workflow(
            CallerWorkflow.run,
            arg=name,
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )


if __name__ == "__main__":
    # Pass a name as a CLI arg to trigger error scenarios:
    #   python -m app.caller.app fail-now   # non-retryable (immediate failure)
    #   python -m app.caller.app retry-me   # retryable (times out after ~30s)
    name = sys.argv[1] if len(sys.argv) > 1 else "world"
    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(execute_caller_workflow(name=name))
        for output in results:
            print(output.message)
    except KeyboardInterrupt:
        loop.run_until_complete(loop.shutdown_asyncgens())
