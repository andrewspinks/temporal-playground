import asyncio

from temporalio.worker import Worker

from app.constants import TASK_QUEUE
from app.shared import connect, setup_logging
from app.workflows import ParentWorkflow, TargetWorkflow


async def main() -> None:
    setup_logging()
    client = await connect("worker")
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TargetWorkflow, ParentWorkflow],
    ):
        print(f"[worker] polling '{TASK_QUEUE}' — Ctrl+C to stop", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
