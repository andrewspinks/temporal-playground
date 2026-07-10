TASK_QUEUE = "pydantic-ai-history-tq"
WORKFLOW_ID = "pydantic-ai-history-demo"

# --- Knobs that drive event-history growth --------------------------------
# These mimic the three levers we saw dominate history size:
#
#   1. NUM_TURNS       — how many model_request activities the agent loop makes.
#                        With TemporalAgent, EACH one re-sends the entire
#                        accumulated conversation as its activity input, so more
#                        turns => bigger tail payloads.
#   2. TOOL_RESULT_KB  — size of each tool result. Tool returns are appended to
#                        the message history and carried forward into every
#                        later model_request input — the dominant growth lever.
#   3. INSTRUCTIONS_KB — size of the system instructions, repeated on messages
#
NUM_TURNS = 12
TOOL_RESULT_KB = 40
INSTRUCTIONS_KB = 20

# --- External storage (claim-check) ---------------------------------------
# Payloads larger than this are offloaded to EXTERNAL_STORAGE_DIR and replaced
# in event history by a small claim reference (see app/storage.py). The
# threshold is deliberately below TOOL_RESULT_KB so the fat tool results — and
# the growing model_request inputs — all get offloaded.
EXTERNAL_STORAGE_THRESHOLD_KB = 32
EXTERNAL_STORAGE_DIR = ".payload-store"
