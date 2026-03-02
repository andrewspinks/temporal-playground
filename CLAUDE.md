# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Polyglot playground for Temporal workflows across Go, TypeScript, Python, Java, .NET, and Ruby SDKs.

## Setup

All toolchain dependencies are managed by [mise](https://mise.jdx.dev/) (see `mise.toml`):

```sh
mise install
```

## Commands (via just)

```sh
just server              # Temporal dev server on localhost:7233
just server-ui           # same, with Web UI on port 8080
just versions            # print all installed tool versions
just history-export WID  # export workflow history JSON (optional: run-id)
just history-replay FILE # replay from saved history
just history-list        # list saved history files
```

Override namespace/address: `just --set namespace prod --set address host:7233 <recipe>`

## Scaffolding TypeScript Projects

Bootstrap from the [official samples repo](https://github.com/temporalio/samples-typescript):

```sh
just new-ts sample=hello-world          # defaults project name to sample name
just new-ts sample=saga name=my-saga    # explicit project name
```

If the directory already exists, the project name auto-increments (`schedules`, `schedules-2`, `schedules-3`, …).

Or let Claude pick the right sample based on what you want to build:

```
/new-ts <describe what you want to build>
```

Claude reads `ts/samples-catalog.md`, selects the best sample, scaffolds the project, and explains the code.

## Structure

- `justfile` — all dev commands
- `mise.toml` — toolchain versions (Go, Node, Python, Java, .NET, Ruby, Temporal CLI, uv, pnpm, gradle)
- `histories/` — exported workflow history JSON files (git-ignored)
- `.cache/` — shallow clones of Temporal samples repos (git-ignored, auto-created)
- `ts/` — TypeScript projects (subdirectories git-ignored); `ts/samples-catalog.md` is tracked
- `.claude/commands/new-ts.md` — `/new-ts` slash command prompt

## Adding a New Language

1. Create `{lang}/samples-catalog.md` from `temporalio/samples-{lang}`
2. Copy `.claude/commands/new-ts.md` → `.claude/commands/new-{lang}.md`, update lang references
3. Replace the `new-{lang}` stub in `justfile` — call `just _clone-samples {lang}`, copy the sample, run language-specific install (`uv sync` for Python, `go mod tidy` for Go, etc.)
