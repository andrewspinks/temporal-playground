import asyncio

from pydantic_ai.durable_exec.temporal import AgentPlugin, PydanticAIPlugin
from temporalio.worker import Worker

from app.agent import temporal_agent
from app.constants import TASK_QUEUE
from app.shared import connect, setup_logging
from app.workflows import DocAnalysisWorkflow


async def main() -> None:
    setup_logging()

    # PydanticAIPlugin (a client+worker plugin) installs the pydantic data
    # converter and the pydantic-ai workflow sandbox. Because it's on the
    # client, the Worker below inherits it automatically.
    client = await connect("pydantic-ai-history-worker", plugins=[PydanticAIPlugin()])

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
