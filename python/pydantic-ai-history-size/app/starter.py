"""Run the agent workflow, then measure the event history it produced.

A single ``just start`` both reproduces the problem and highlights it: it starts
``DocAnalysisWorkflow``, waits for the result, then pulls the workflow history
and prints the size breakdown + model_request input growth curve (see
``app/analyze.py``).
"""

import asyncio
import time

from google.protobuf.json_format import MessageToDict
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from app.analyze import analyze_events
from app.constants import TASK_QUEUE, WORKFLOW_ID
from app.shared import connect
from app.workflows import DocAnalysisWorkflow

PROMPT = "Review the incoming documents and report your findings."


async def main() -> None:
    # Same plugin as the worker so the client's data converter can decode the
    # pydantic AnalysisResult result.
    client = await connect("starter", plugins=[PydanticAIPlugin()])

    wf_id = f"{WORKFLOW_ID}-{int(time.time())}"
    handle = await client.start_workflow(
        DocAnalysisWorkflow.run,
        PROMPT,
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"workflow_id={wf_id}")

    result = await handle.result()
    print(f"result: summary={result.summary!r} findings={len(result.findings)}")

    # Convert the fetched protobuf history to the same JSON shape the analyzer
    # uses for exported-history files (camelCase fields, bytes as base64).
    history = await handle.fetch_history()
    events = [MessageToDict(e) for e in history.events]
    analyze_events(events)


if __name__ == "__main__":
    asyncio.run(main())
