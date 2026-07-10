import asyncio

from pydantic_ai.durable_exec.temporal import AgentPlugin, PydanticAIPlugin
from temporalio.worker import Worker

from app.agent import temporal_agent
from app.constants import EXTERNAL_STORAGE_THRESHOLD_KB, TASK_QUEUE
from app.shared import connect, setup_logging
from app.storage import build_data_converter
from app.workflows import DocAnalysisWorkflow


async def main() -> None:
    setup_logging()

    # PydanticAIPlugin (a client+worker plugin) installs the pydantic-ai
    # workflow sandbox and validates the data converter. We pass a converter =
    # pydantic converter + external storage; the plugin keeps it as-is (it's
    # still a PydanticPayloadConverter). Payloads over the threshold are
    # offloaded off-history to the local store.
    print(
        f"[worker] external storage: payloads > {EXTERNAL_STORAGE_THRESHOLD_KB} KB → local disk"
    )
    client = await connect(
        "pydantic-ai-history-worker",
        plugins=[PydanticAIPlugin()],
        data_converter=build_data_converter(),
    )

    # AgentPlugin registers this agent's activities (model_request + one
    # call_tool activity per tool) on the worker.
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DocAnalysisWorkflow],
        plugins=[AgentPlugin(temporal_agent)],
    ):
        print(f"[worker] polling '{TASK_QUEUE}' — Ctrl+C to stop")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
