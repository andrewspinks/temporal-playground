# Java Nexus caller and handler

A Nexus service exposed by a Java handler and invoked by a Java caller workflow in a **different
namespace**, with credentials to match — the two sides may live in different Temporal Cloud accounts.

The service does one thing (fetch a todo from `jsonplaceholder.typicode.com`) through **two kinds of
operation**, so the difference between them is visible from the caller's side.

Java SDK 1.35.0, `io.nexusrpc:nexus-sdk` 0.5.0-alpha.

## The two operation kinds

```
JobService
├─ fetchTodoSync    OperationHandler.sync
│     └─ calls TodoApi directly, inline in the handler
│        HARD 10s deadline · no execution to inspect · no token
│
└─ fetchTodoAsync   WorkflowRunOperation.fromWorkflowMethod
      └─ FetchTodoWorkflow → TodoActivities → TodoApi
         no ceiling · durable execution · caller holds an operation token
```

| | `fetchTodoSync` | `fetchTodoAsync` |
|---|---|---|
| Handler | `OperationHandler.sync` | `WorkflowRunOperation` |
| Duration ceiling | **10s, fixed** | none |
| Caller gets a token | no | yes |
| Leaves a durable execution | no | yes (a workflow) |
| Retries, timers, signals available | no | yes |
| Errors surface as | `HandlerException` | activity `ApplicationFailure` |

A caller cannot tell them apart from the contract — that is the point of Nexus. But the ceiling is
real: sync operations must finish within a fixed **10 seconds**, and handlers that overrun are retried
until the operation's schedule-to-close expires. Slow work in a sync handler becomes *repeated* work,
not a slow success. Anything whose latency is not predictably small belongs in the workflow-backed one.

Both paths call the same [`TodoApi`](src/main/java/io/temporal/nexusjobs/todo/TodoApi.java), which is
deliberately free of Temporal types. That is what lets each side map identical failures onto its own
error model — `HandlerException` with `NOT_FOUND` / `UNAVAILABLE` for the sync operation, retryable and
non-retryable `ApplicationFailure` for the activity.

## Layout

```
HANDLER_NAMESPACE  ← handler profile's credentials
└── java-handler-task-queue      ← NexusHandlerWorker
       endpoint: Nexus-java-endpoint
       Nexus tasks    → JobServiceImpl
       workflow tasks → FetchTodoWorkflowImpl
       activity tasks → TodoActivitiesImpl

CALLER_NAMESPACE   ← caller profile's credentials (possibly a different account)
└── java-caller-task-queue       ← CallerWorker + CallerStarter
       JobCallerWorkflowImpl calls both operations
```

One worker on one task queue serves all three task types. Two workers total.

| File | Role |
|---|---|
| [`service/JobService`](src/main/java/io/temporal/nexusjobs/service/JobService.java) | The contract — shared by both sides |
| [`handler/JobServiceImpl`](src/main/java/io/temporal/nexusjobs/handler/JobServiceImpl.java) | Both operation handlers |
| [`handler/FetchTodoWorkflowImpl`](src/main/java/io/temporal/nexusjobs/handler/FetchTodoWorkflowImpl.java) | Workflow behind the async operation |
| [`handler/NexusHandlerWorker`](src/main/java/io/temporal/nexusjobs/handler/NexusHandlerWorker.java) | Handler worker |
| [`caller/JobCallerWorkflowImpl`](src/main/java/io/temporal/nexusjobs/caller/JobCallerWorkflowImpl.java) | Calls both operations, times each |
| [`caller/CallerWorker`](src/main/java/io/temporal/nexusjobs/caller/CallerWorker.java) / [`CallerStarter`](src/main/java/io/temporal/nexusjobs/caller/CallerStarter.java) | Caller worker and starter |
| [`todo/TodoApi`](src/main/java/io/temporal/nexusjobs/todo/TodoApi.java) | The actual work, Temporal-free |
| [`Config`](src/main/java/io/temporal/nexusjobs/Config.java) | Names + per-role profile loading |

## Configuration — two identities, two credentials

The handler and the caller are separate namespaces and may be separate Cloud accounts, so they need
**separate API keys**. That rules out the ambient `TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE` /
`TEMPORAL_API_KEY` variables: there is one of each per process, and one key cannot authenticate to two
accounts.

Instead each program declares its role and loads the matching **envconfig profile**, which carries
that role's own address, namespace, and `api_key`:

```sh
cp temporal.toml.example temporal.toml   # then fill in the two api_key values
```

```toml
[profile.handler]
address   = "us-east-1.aws.api.temporal.io:7233"
namespace = "playground-nexus-handler.yy98u"
api_key   = "..."

[profile.caller]
address   = "us-east-1.aws.api.temporal.io:7233"
namespace = "playground-nexus-caller.yy98u"
api_key   = "..."      # a different key, possibly a different account
```

Profile names come from `HANDLER_PROFILE` / `CALLER_PROFILE` (defaults `handler` / `caller`), so
switching to the local dev server is a matter of pointing at different profiles:

```sh
cp .env.local.example .env   # HANDLER_PROFILE=handler-local, CALLER_PROFILE=caller-local
```

The `temporal` CLI reads the same file and profiles, so SDK and CLI stay in sync:

```sh
temporal --config-file ./temporal.toml --profile handler workflow list
```

> **Do not set `TEMPORAL_API_KEY`, `TEMPORAL_ADDRESS`, or `TEMPORAL_NAMESPACE`.** envconfig applies env
> vars *on top of* the loaded profile, so any of them overrides **every** profile with a single value —
> silently collapsing the two identities into one. `temporal.toml` and `.env*` are gitignored.

If a named profile is missing, `Config.loadProfile` prints
`No 'handler' profile found … falling back to env-var config` and continues on env vars. Watch for
that line — it means the profile name or config path is wrong.

## Running it

One-time endpoint setup, from `playground/nexus/`:

```sh
just java-setup         # Cloud: creates the endpoint, then grants the caller namespace via tcld
just java-setup-local   # dev server: creates both namespaces and the endpoint
```

Cloud requires the caller-namespace grant even within a single account, and
`temporal operator nexus endpoint create` has **no flag for it** — so `tcld` does that step, with its
own `TEMPORAL_CLOUD_API_KEY` (a control-plane credential, distinct from the two profile keys).
Namespaces must already exist; Cloud does not create them through this CLI.

Then:

```sh
just java-build          # once — parallel `gradlew run` on a cold build/ races
just java-handler        # terminal 1
just java-caller-worker  # terminal 2
just java-caller         # terminal 3
```

```
  fetchTodoSync  (handled inline)      : Todo{userId=1, id=1, title='delectus aut autem', completed=false}
      took 355ms — capped at 10s by the Nexus handler deadline
  fetchTodoAsync (backed by workflow)  : Todo{userId=1, id=1, title='delectus aut autem', completed=false}
      took 284ms — no 10s ceiling
```

`just java-caller` uses todo 1. For another:
`cd java && ./gradlew -q run -PmainClass=io.temporal.nexusjobs.caller.CallerStarter --args="7"`.
Id `9999` is a 404 — see below.

## What to look at

The caller's history distinguishes the two operation kinds plainly:

```sh
temporal workflow show --workflow-id job-caller-todo-1 --namespace $CALLER_NAMESPACE | grep Nexus
```

```
 5  NexusOperationScheduled     ← fetchTodoSync
 6  NexusOperationCompleted        no Started event: it completed inline in the handler's response
10  NexusOperationScheduled     ← fetchTodoAsync
11  NexusOperationStarted          the token handoff
15  NexusOperationCompleted        delivered later, via the operation's callback
```

The async operation also leaves a workflow in the handler namespace, which the sync one does not:

```sh
temporal workflow list --namespace $HANDLER_NAMESPACE   # FetchTodoWorkflow, id fetch-todo-1
```

**Error mapping.** Todo `9999` is a 404. The sync operation raises `HandlerException(NOT_FOUND)` —
non-retryable by default, so the caller fails fast instead of burning its schedule-to-close. The async
operation's activity raises a non-retryable `ApplicationFailure`, so the workflow fails and the failure
reaches the caller as a `NexusOperationError`.

**The 10s ceiling.** To watch it bite, add a `Thread.sleep(12_000)` to `TodoApiClient.fetch` and run the
caller. `fetchTodoSync` fails with `TimeoutFailure timeoutType=TIMEOUT_TYPE_SCHEDULE_TO_CLOSE` after the
caller's 30s, having been retried roughly every 10s — and the work will have run more than once.
`fetchTodoAsync` is unaffected.

## Why this handler has its own endpoint

A Nexus endpoint maps to exactly one (namespace, task queue). Sharing the playground's Python handler
endpoint would mean sharing `my-handler-task-queue` — and Temporal hands a Nexus task to whichever
worker polls first, with **no routing by service name**. Roughly half of all tasks would reach a worker
that has never heard of the requested service.

That produces a `NOT_FOUND` handler error, which is **non-retryable by default**, so those operations
fail permanently rather than being redelivered. Both services break, intermittently. One endpoint
serving two languages would require a single worker registering both services.

To watch it happen — local dev server only, since it needs the Python handler:

```sh
cp .env.local.example .env
just handler                # Python handler on my-handler-task-queue
just java-collision-demo    # Java handler on the SAME queue
just py-caller              # a few times
```

`just py-caller`'s `say_hello` times out after ~30s even when healthy — the Python `SayHelloWorkflow`
waits on a `complete` signal by design. Its *sync* operation is the part to watch for `NOT_FOUND`.

## Notes

- **Java 21.** The root `mise.toml` uses `java = "latest"` (26), which breaks the Gradle 8.10.2 wrapper.
  This project's `mise.toml` pins 21.
- The caller names the endpoint on its stub. To keep it out of workflow code, set it at worker
  registration with `WorkflowImplementationOptions.setNexusServiceOptions` — see `CallerWorker`.
- No tests yet. `JobServiceImpl` takes `TodoApi` by constructor precisely so a handler test can pass a
  fake instead of hitting the network.
