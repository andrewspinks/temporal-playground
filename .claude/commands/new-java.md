Bootstrap a new Java Temporal project from the official samples.

User's request: $ARGUMENTS

## Steps

1. Read `java/samples-catalog.md` to understand the available samples.

2. Based on the user's description, select the most appropriate sample. Prefer simpler samples when the request is basic — don't over-engineer. If the request is ambiguous, briefly present your top 2-3 options with one sentence each and ask which fits best.

3. Choose a short, descriptive kebab-case project name that reflects what the user is building (not just the sample name).

4. Bootstrap the project using positional arguments (not `key=value` syntax):
   ```
   just new-java <sample-name> <project-name>
   ```

5. After the project is created, give the user a brief orientation:
   - What the sample demonstrates and why you chose it
   - The key files and their roles (Workflow interface + impl, Activity interface + impl, Worker starter, Workflow starter)
   - How to run it: `cd java/<project-name>`, start the Temporal server (`just server` from the playground root in a separate terminal), then run the main class:
     ```
     ./gradlew run -PmainClass=io.temporal.samples.<sample>.<MainClass>
     ```
   - What to change first to adapt the sample to their use case

## Notes

- The playground uses Gradle (not Maven). The generated project uses the Gradle wrapper (`./gradlew`).
- The Temporal dev server is started with `just server` in a separate terminal.
- The `hello` sample contains 30+ self-contained `Hello*.java` files — each is independently runnable. When the user picks `hello`, suggest the most relevant sub-file (e.g. `HelloActivity` for basics, `HelloSignal` for signals, etc.).
- Use the `temporal-docs` MCP tool if you need to look up Temporal concepts while explaining.
- If the user's need isn't covered by any sample, pick the closest one (often `hello`) and explain what they'll need to add.
