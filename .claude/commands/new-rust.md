Bootstrap a new Rust Temporal hello-world project.

User's request: $ARGUMENTS

## Steps

1. Choose a short, descriptive kebab-case project name based on the user's request. Default to "hello-world" if the request is vague.

2. Bootstrap the project (arguments are positional):
   ```
   just new-rust <project-name>
   ```
   To pin specific versions:
   ```
   just new-rust <project-name> 0.1.0-alpha.1 1.85.0
   ```
   (arguments: name, sdk_version, rust_version)

3. After the project is created, give the user a brief orientation:
   - What the generated project contains (a `GreetingWorkflow` that calls a `greet` activity returning "Hello, World!")
   - The key files and their roles:
     - `src/activities.rs` — `MyActivities` struct with `greet` activity
     - `src/workflows.rs` — `GreetingWorkflow` that calls the activity
     - `src/bin/worker.rs` — connects to Temporal server and runs the worker
     - `src/bin/starter.rs` — starts the workflow and prints the result
   - How to run it:
     1. Start the Temporal server: `just server` from the playground root (separate terminal)
     2. `cd rust/<project-name>`
     3. `just worker` (separate terminal) — starts the worker
     4. `just start` — triggers the workflow and prints the result
   - What to change first to adapt the project (rename `GreetingWorkflow`, add activities, etc.)

## Notes

- The Temporal Rust SDK (`temporalio-sdk`) is prerelease (alpha). The API may evolve — check the [README](https://github.com/temporalio/sdk-core/blob/master/crates/sdk/README.md) if anything doesn't compile.
- There is no official samples repo for Rust yet. The project is generated from a hello-world template.
- First build takes a while — Cargo downloads and compiles all dependencies.
- Use the `temporal-docs` MCP tool if you need to look up Temporal concepts while explaining.
