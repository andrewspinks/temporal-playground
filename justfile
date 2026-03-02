# Temporal Playground — Task Runner

# Dev server ─────────────────────────────────────────────

# Start Temporal dev server
server:
    temporal server start-dev

# Start Temporal dev server with UI on port 8080
server-ui:
    temporal server start-dev --ui-port 8080

# Setup ──────────────────────────────────────────────────

# Install all toolchain dependencies via mise
setup:
    mise install

# Print installed tool versions
versions:
    @echo "just     $(just --version)"
    @echo "go       $(go version)"
    @echo "node     $(node --version)"
    @echo "python   $(python --version)"
    @echo "java     $(java --version 2>&1 | head -1)"
    @echo "dotnet   $(dotnet --version)"
    @echo "temporal $(temporal --version)"
    @echo "uv       $(uv --version)"
    @echo "pnpm     $(pnpm --version)"
    @echo "ruby     $(ruby --version)"
    @echo "gradle   $(gradle --version | grep Gradle)"

# History export & replay ──────────────────────────────

# Default connection settings (override with `just --set namespace prod ...`)
namespace := "default"
address := "localhost:7233"

# Export workflow history as JSON
history-export workflow-id run-id="":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p histories
    args=(--workflow-id "{{workflow-id}}" --namespace "{{namespace}}" --address "{{address}}" --output json)
    if [ -n "{{run-id}}" ]; then
        args+=(--run-id "{{run-id}}")
    fi
    out="histories/{{workflow-id}}.json"
    temporal workflow show "${args[@]}" > "$out"
    echo "Exported to $out"

# Replay a workflow from a saved history file
history-replay file:
    temporal workflow replay --file "{{file}}" --namespace "{{namespace}}" --address "{{address}}"

# List saved history files
history-list:
    @ls -1 histories/*.json 2>/dev/null || echo "No history files found in histories/"

# Scaffolding (future) ──────────────────────────────────

# Scaffold a new Go project
new-go name="hello":
    @echo "TODO: scaffold Go project '{{name}}'"

# Scaffold a new TypeScript project
new-ts name="hello":
    @echo "TODO: scaffold TypeScript project '{{name}}'"

# Scaffold a new Python project
new-py name="hello":
    @echo "TODO: scaffold Python project '{{name}}'"

# Scaffold a new Java project
new-java name="hello":
    @echo "TODO: scaffold Java project '{{name}}'"

# Scaffold a new Ruby project
new-ruby name="hello":
    @echo "TODO: scaffold Ruby project '{{name}}'"

# Scaffold a new .NET project
new-dotnet name="hello":
    @echo "TODO: scaffold .NET project '{{name}}'"
