import asyncio

from temporalio.worker import Worker

from app.activities import store_secret
from app.keyring import CURRENT_KEY_ID, TASK_QUEUE, connect
from app.workflows import SecretVaultWorkflow

# The worker holds the FULL keyring (via `connect`) so it can decrypt payloads
# written with any key, and encrypts new payloads (activity inputs, workflow
# results) with the newest key.
interrupt_event = asyncio.Event()


async def main() -> None:
    client = await connect(CURRENT_KEY_ID)
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[SecretVaultWorkflow],
        activities=[store_secret],
    ):
        print(f"Worker started (active key {CURRENT_KEY_ID!r}); ctrl+c to exit")
        await interrupt_event.wait()
        print("Shutting down")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        interrupt_event.set()
        loop.run_until_complete(loop.shutdown_asyncgens())
