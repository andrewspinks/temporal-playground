Bootstrap a new TypeScript Temporal project from the official samples.

User's request: $ARGUMENTS

## Steps

1. Read `ts/samples-catalog.md` to understand the available samples.

2. Based on the user's description, select the most appropriate sample. Prefer simpler samples when the request is basic — don't over-engineer. If the request is ambiguous, briefly present your top 2-3 options with one sentence each and ask which fits best.

3. Choose a short, descriptive kebab-case project name that reflects what the user is building (not just the sample name).

4. Bootstrap the project using positional arguments (not `key=value` syntax):
   ```
   just new-ts <sample-name> <project-name>
   ```

5. After the project is created, give the user a brief orientation:
   - What the sample demonstrates and why you chose it
   - The key files and their roles (`worker.ts`, `workflows.ts`, `activities.ts`, `client.ts`)
   - How to run it: `cd ts/<project-name>`, start the Temporal server (`just server` from the playground root), then the worker (`pnpm run start`), then the client (`pnpm run workflow`)
   - What to change first to adapt the sample to their use case

## Notes

- The playground uses `pnpm` (not npm or yarn).
- The Temporal dev server is started with `just server` in a separate terminal.
- Use the `temporal-docs` MCP tool if you need to look up Temporal concepts while explaining.
- If the user's need isn't covered by any sample, pick the closest one (often `hello-world`) and explain what they'll need to add.
