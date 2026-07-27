# .NET Hello World

Minimal Temporal hello-world using the [.NET SDK](https://github.com/temporalio/sdk-dotnet) (`Temporalio` **1.9.0**).

## Layout

- `Activities.cs` — `GreetingActivities.SayHello`, a plain activity that returns a greeting.
- `Workflow.cs` — `SayHelloWorkflow`, executes the activity.
- `Program.cs` — single entry point; dispatches to worker or starter based on the first arg.

## Run

Start the Temporal dev server (from the repo root):

```sh
just server
```

Then, in one terminal, run the worker:

```sh
cd dotnet/hello-world
just worker
```

In another terminal, start a workflow:

```sh
cd dotnet/hello-world
just start          # greets "Temporal"
just start Andy     # greets "Andy"
```

Expected output from the starter:

```
Workflow result: Hello, Andy!
```

## Connection

The worker/starter connect to `TEMPORAL_ADDRESS` (env var), defaulting to `localhost:7233`.
