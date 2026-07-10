"""Run the agent workflow, then measure the event history it produced.

``just start`` starts ``DocAnalysisWorkflow``, waits for the result, then pulls
the workflow history and prints the size breakdown + model_request input growth
curve (see ``app/analyze.py``). Because the worker and this client use external
storage, the fat payloads are offloaded off-history — so the report shows a tiny,
flat history instead of the multi-MB bloat you'd get without it.
"""

import asyncio
import os
import time

from google.protobuf.json_format import MessageToDict
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from app.analyze import analyze_events
from app.constants import EXTERNAL_STORAGE_DIR, TASK_QUEUE, WORKFLOW_ID
from app.shared import connect
from app.storage import build_data_converter
from app.workflows import DocAnalysisWorkflow

PROMPT = "Review the incoming documents and report your findings."


def _store_stats() -> tuple[int, int]:
    files = total = 0
    for root, _, names in os.walk(EXTERNAL_STORAGE_DIR):
        for n in names:
            files += 1
            total += os.path.getsize(os.path.join(root, n))
    return files, total


async def main() -> None:
    # Same plugin + data converter as the worker, so the client stores/retrieves
    # claims consistently and can decode the pydantic AnalysisResult result.
    client = await connect(
        "starter",
        plugins=[PydanticAIPlugin()],
        data_converter=build_data_converter(),
    )

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

    files, b = _store_stats()
    print(
        f"\nexternal store ({EXTERNAL_STORAGE_DIR}): {files} objects, "
        f"{b:,} bytes ({b / 1024 / 1024:.2f} MB) offloaded off-history."
    )


if __name__ == "__main__":
    asyncio.run(main())
