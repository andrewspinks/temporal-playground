from datetime import timedelta
from typing import List

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.activities import store_secret


@workflow.defn
class SecretVaultWorkflow:
    """Collects secrets over its lifetime, then returns them all on `finish`.

    This workflow is designed to OUTLIVE a key rotation: its input and early
    signals are encrypted with one key, later signals with another, and its
    result with whatever key the worker is on. Every one of those payloads
    lands in the same workflow history, encrypted under a mix of keys.
    """

    def __init__(self) -> None:
        self._secrets: List[str] = []
        self._done = False

    @workflow.run
    async def run(self, initial_secret: str) -> List[str]:
        await self._add(initial_secret)
        await workflow.wait_condition(lambda: self._done)
        return self._secrets

    async def _add(self, secret: str) -> None:
        # Round-trip through an activity so activity payloads are encrypted too.
        confirmation = await workflow.execute_activity(
            store_secret,
            secret,
            start_to_close_timeout=timedelta(seconds=10),
        )
        workflow.logger.info(f"activity said: {confirmation}")
        self._secrets.append(secret)

    @workflow.signal
    async def add_secret(self, secret: str) -> None:
        await self._add(secret)

    @workflow.signal
    def finish(self) -> None:
        self._done = True

    @workflow.query
    def get_secrets(self) -> List[str]:
        return self._secrets
