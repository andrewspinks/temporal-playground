# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
just worker       # start the Worker (run first, in a separate terminal)
just start        # run the Workflow starter
just build        # cargo build
just lint         # cargo fmt + cargo clippy
cargo test        # run tests (no server needed)
```

After every code change, run `just lint && cargo test` to verify formatting, linting, and tests all pass.

Requires a Temporal server running on `localhost:7233` for `just worker` / `just start` (`just server` from the repo root).

## Architecture

This is a hello-world Temporal workflow project using the Rust SDK (prerelease `0.1.0-alpha.1`). Workspace members: the main crate and `temporal-test-harness/`.

**Entry points:**
- `src/bin/worker.rs` — connects to Temporal, registers activities and workflows, runs the worker loop
- `src/bin/starter.rs` — connects to Temporal, starts `GreetingWorkflow` with input `"World"`, prints the run ID

**Library (`src/lib.rs` re-exports two modules):**
- `src/workflows.rs` — defines `GreetingWorkflow` using `#[workflow]` / `#[workflow_methods]` macros; the `pub #[run]` method takes `name: String` directly and calls `greet` via `ctx.start_activity(...)`
- `src/activities.rs` — defines `MyActivities` with a single `greet(name) -> String` activity using `#[activities]` / `#[activity]` macros

**Tests:**
- `tests/workflow_test.rs` — integration-style tests using `temporal-test-harness` (mock worker, no server)
- `temporal-test-harness/` — generic test harness subcrate adapted from `temporalio/temporal-money-transfer-project-rust`

**Key SDK crates:**
- `temporalio-sdk` — `Worker`, `WorkerOptions`, `WorkflowContext`, `ActivityOptions`
- `temporalio-client` — `Client`, `Connection`, `WorkflowStartOptions`
- `temporalio-macros` — `#[workflow]`, `#[workflow_methods]`, `#[activities]`, `#[activity]`
- `temporalio-sdk-core` — `CoreRuntime`, `RuntimeOptions`

The task queue name is `"greeting-task-queue"` and the workflow ID is `"greeting-workflow-1"`.

## Known SDK Quirks (alpha)

- **Use `edition = "2024"`** — required for the macros to compile correctly with current Rust.
- **Workflow structs must be unit structs with `#[derive(Default)]`** — the `#[init]` pattern (named fields + constructor) triggers `E0446` due to a visibility bug in the `#[workflow_methods]` macro. Pass input directly to the `#[run]` method instead.
- **`#[run]` must be `pub`**.
- **`Client::new(...)` returns `Result`** — always add `?`; the alpha.1 infallible form is gone.
- **No `start_workflow_typed`** — use `client.start_workflow(WorkflowType, input, WorkflowStartOptions::new(queue, id).build())`.
- **Getting a result** — use `handle.get_result(WorkflowGetResultOptions::default()).await?`.

## References

### Rust SDK
- **README with examples**: https://github.com/temporalio/sdk-core/blob/master/crates/sdk/README.md
  - Activities (error types, local activities, shared state via `Arc<Self>`)
  - Workflows (signals, queries, updates, timers, child workflows, continue-as-new, patching/versioning)
  - Worker configuration options (`max_cached_workflows`, `graceful_shutdown_period`, etc.)
  - Client usage (signals, queries, updates, cancel/terminate, list workflows)
- **API docs**: https://docs.rs/temporalio-sdk

### Temporal Advice
Use the `mcp__temporal-docs__search_temporal_knowledge_sources` tool (available in this Claude Code session) to look up Temporal concepts, patterns, and best practices. For example:
- "How do I implement the saga pattern in Temporal?"
- "What are Temporal workflow determinism constraints?"
- "How does Temporal handle activity retries?"
