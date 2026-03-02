# Temporal Playground

A polyglot playground for experimenting with Temporal workflows across all five official SDKs (Go, TypeScript, Python, Java, .NET).

## Prerequisites

Install [mise](https://mise.jdx.dev/) — it manages all other toolchain dependencies automatically.

## Setup

```sh
mise install   # install all tools (Go, Node, Python, Java, .NET, Temporal CLI, etc.)
```

## Available Recipes

Run `just --list` to see all recipes. Highlights:

| Recipe | Description |
|--------|-------------|
| `just server` | Start Temporal dev server |
| `just server-ui` | Start dev server with UI on port 8080 |
| `just setup` | Run `mise install` |
| `just versions` | Print installed tool versions |
| `just new-go` | Scaffold a Go project (placeholder) |
| `just new-ts` | Scaffold a TypeScript project (placeholder) |
| `just new-py` | Scaffold a Python project (placeholder) |
| `just new-java` | Scaffold a Java project (placeholder) |
| `just new-ruby` | Scaffold a Ruby project (placeholder) |
| `just new-dotnet` | Scaffold a .NET project (placeholder) |
