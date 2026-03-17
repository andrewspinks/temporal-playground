# Reproducing: `IllegalStateError: Root workflow execution is missing a field that should be defined`

## Background

When a child workflow is spawned from a parent that was started on a Temporal server
**before v1.24.0** (which added `RootWorkflowId`/`RootRunId` to mutable state), and
the server has since been upgraded to v1.24.0+, the child receives an empty
`rootWorkflowExecution: {}` instead of a properly populated one or `null`.

The TypeScript SDK (v1.12.0+) throws `IllegalStateError` on this empty object,
crashing the child workflow.

### Root cause

1. Parent started on server < v1.24.0. Its mutable state has `RootWorkflowId = ""`
   and `RootRunId = ""` (proto3 default empty strings -- fields didn't exist yet).
2. Server upgrades to v1.24.0+. No backfill migration populates these fields.
3. Mutable state is loaded from DB (not rebuilt from history), so empty strings persist.
4. Parent spawns a child. Server propagates the empty strings as
   `rootWorkflowExecution: { workflowId: "", runId: "" }` which serializes as `{}`.
5. SDK's `convertToRootWorkflowType` sees a non-null object with falsy fields and throws.

## Setup

This repo uses two git branches/worktrees:

| Worktree | Branch | Server | SDK |
|---|---|---|---|
| `child-workflow-bug-old-version` | `child-workflow-bug-old-version` | 1.23.0 (pre-feature) | 1.11.8 |
| `child-workflow-bug-new` | `child-workflow-bug-updated` | 1.27.1 (post-feature) | 1.15.0 |

Both share a Postgres Docker volume (`temporal-repro-pgdata`) so the DB persists
across the server upgrade.

### Checking out the worktrees

```bash
# From your temporal-playground repo root:
git worktree add ../worktrees/child-workflow-bug-old-version child-workflow-bug-old-version
git worktree add ../worktrees/child-workflow-bug-new child-workflow-bug-updated
```

### Install dependencies

```bash
# Old version
cd worktrees/child-workflow-bug-old-version/ts/child-continue-as-new
npm install

# New version
cd worktrees/child-workflow-bug-new/ts/child-continue-as-new
npm install
```

## Reproduction steps

### 0. Clean up any previous runs

```bash
# From either worktree's ts/child-continue-as-new directory:
docker compose down
docker volume rm temporal-repro-pgdata
```

### 1. Start parent workflow on OLD server (pre v1.24.0)

```bash
cd worktrees/child-workflow-bug-old-version/ts/child-continue-as-new

# Start old server (1.23.0) + Postgres + UI
docker compose up
# or: mise run server

# In another terminal, start the worker (SDK 1.11.8)
npm start

# In another terminal, start the parent workflow
temporal workflow start \
  --address localhost:7234 \
  --task-queue child-workflows \
  --type parentWorkflow \
  --workflow-id parent-repro-0
# or: mise run start-parent
```

Verify the parent is running (waiting for signal) at http://localhost:8234.

### 2. Stop old server and worker

```bash
# Stop the worker (Ctrl+C in its terminal)

# Stop the server (keeps the Postgres volume)
docker compose down
# or: mise run server-down
```

### 3. Start NEW server and worker

```bash
cd worktrees/child-workflow-bug-new/ts/child-continue-as-new

# Start new server (1.27.1) -- auto-setup runs DB migrations
docker compose up
# or: mise run server

# In another terminal, start the worker (SDK 1.15.0)
npm start
```

### 4. Trigger the bug

```bash
# Signal the parent to spawn a child
temporal workflow signal \
  --address localhost:7234 \
  --workflow-id parent-repro-0 \
  --name spawnChild
# or: mise run signal
```

### Expected result

The worker logs should show:

```
IllegalStateError: Root workflow execution is missing a field that should be defined
    at convertToRootWorkflowType (...)
    at Worker.createWorkflow (...)
```

The child workflow (`child-Alice`) will show `WORKFLOW_TASK_FAILED` in the UI at
http://localhost:8234.

### Verify the empty rootWorkflowExecution

```bash
temporal workflow show \
  --address localhost:7234 \
  --workflow-id child-Alice \
  --output json | head -50
```

You should see `"rootWorkflowExecution": {}` in the child's first event.

## Key version boundaries

- **Server v1.24.0**: Added `RootWorkflowId`/`RootRunId` to mutable state persistence
  (commit `ef1f1439c`). Workflows started before this have empty strings in DB.
- **SDK v1.12.0**: Added `convertToRootWorkflowType` which throws on empty fields
  (commit `70864b6d`).
