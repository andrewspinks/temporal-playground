"""Offline, deterministic model that drives a fixed multi-turn tool loop.

The history size problem only shows up over a *long* agent loop: history grows
because every turn re-sends the whole conversation. ``TestModel`` calls each
tool exactly once and then stops, so it can't reproduce that. A ``FunctionModel``
lets us script exactly ``NUM_TURNS`` turns with no API key and no network:

    turns 1 .. NUM_TURNS-1 : call ``fetch_document`` (each call appends a fat
                             ToolReturnPart to the message history)
    turn  NUM_TURNS        : emit the structured final output

Each call to ``model_function`` below happens *inside* a Temporal
``model_request`` activity (TemporalAgent offloads model calls to activities),
and its input is the full ``messages`` list — which is exactly why the
ACTIVITY_TASK_SCHEDULED payloads grow turn over turn.

To use a real model instead, see ``app/agent.py`` — you don't touch this file.
"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.constants import NUM_TURNS

TOOL_NAME = "fetch_document"


def _turns_taken(messages: list[ModelMessage]) -> int:
    """How many times the model has already responded == turns completed."""
    return sum(1 for m in messages if isinstance(m, ModelResponse))


def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    turn = _turns_taken(messages)

    # Keep looping: request another document. Each result is a fat blob that
    # gets appended to the history and carried forward into every later turn.
    if turn < NUM_TURNS - 1:
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name=TOOL_NAME, args={"doc_id": f"doc-{turn:03d}"})
            ]
        )

    # Final turn: produce the structured output. With a Pydantic ``output_type``
    # pydantic-ai exposes an output tool; call it with a valid instance. If the
    # agent allowed plain text output instead, fall back to a text part.
    if info.output_tools:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={
                        "summary": (
                            f"Reviewed {turn} documents; see findings for details."
                        ),
                        "findings": [
                            {"doc_id": f"doc-{i:03d}", "verdict": "ok", "score": 0.9}
                            for i in range(turn)
                        ],
                    },
                )
            ]
        )
    return ModelResponse(parts=[TextPart(content=f"Reviewed {turn} documents.")])


def build_function_model() -> FunctionModel:
    return FunctionModel(model_function, model_name="scripted-loop")
