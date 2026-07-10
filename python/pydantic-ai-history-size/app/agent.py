"""The agent, its tool, and its structured output — wrapped as a TemporalAgent.

This is a deliberately generic "document analysis" agent, but shaped to
reproduce the three things that inflated the event history:

  * a large ``instructions`` blob (repeated on the messages every turn),
  * a tool whose result is a large blob (``fetch_document``), and
  * a non-trivial structured ``output_type`` (adds a big output-tool JSON
    schema to ``model_request_parameters``, sent on every model_request).

Wrapping the plain ``Agent`` in ``TemporalAgent`` is what turns every model
call and every tool call into a Temporal activity — and what causes the whole
conversation to be re-sent as each ``model_request`` activity's input.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalAgent

from app.constants import INSTRUCTIONS_KB, TOOL_RESULT_KB
from app.model import build_function_model

AGENT_NAME = "doc-analysis"

# A big instructions string, mimicking the large
# instructions. pydantic-ai attaches instructions to the request messages, so
# this weight rides along in every model_request activity input.
INSTRUCTIONS = (
    "You are a meticulous document-analysis assistant. Review each document "
    "carefully and report findings. "
) + ("Follow the detailed review policy below. " * (INSTRUCTIONS_KB * 1024 // 40))


class Finding(BaseModel):
    """One reviewed document."""

    doc_id: str
    verdict: str
    score: float


class AnalysisResult(BaseModel):
    """Structured final output — its JSON schema is sent on every model_request."""

    summary: str
    findings: list[Finding]


def _fat_blob(doc_id: str) -> str:
    """A large, unique-ish document body (~TOOL_RESULT_KB)."""
    line = f"[{doc_id}] lorem ipsum dolor sit amet consectetur adipiscing elit "
    return (line * (TOOL_RESULT_KB * 1024 // len(line)))[: TOOL_RESULT_KB * 1024]


def build_agent() -> Agent[None, AnalysisResult]:
    # ---- Offline default: scripted FunctionModel (no API key, deterministic).
    model = build_function_model()
    # ---- Real-model switch: install the `real` extra + set OPENAI_API_KEY, then
    #      replace the line above with:
    #          model = "openai:gpt-4o"
    #      Nothing else in this file changes. Note a real model makes the turn
    #      count (and thus the history size) vary run-to-run.

    agent = Agent(
        model=model,
        name=AGENT_NAME,
        instructions=INSTRUCTIONS,
        output_type=AnalysisResult,
    )

    @agent.tool_plain
    def fetch_document(doc_id: str) -> str:
        """Fetch a document's full text by id."""
        return _fat_blob(doc_id)

    return agent


# Module-level so the workflow can call it and the worker can register its
# activities (``temporal_agent.temporal_activities``).
temporal_agent = TemporalAgent(build_agent(), name=AGENT_NAME)
