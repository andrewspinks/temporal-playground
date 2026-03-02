# TypeScript Temporal Samples Catalog

Catalog of samples from [temporalio/samples-typescript](https://github.com/temporalio/samples-typescript).
Used by Claude to select the best starting point for a new project.

> To see what's currently in the cache: `ls .cache/samples-typescript/`

---

## Basic / Getting Started

### hello-world
**Description**: Canonical minimal example — one Workflow, one Activity, a Worker, and a Client.
**Use when**: Starting from scratch, learning the basics, or you need a clean simple template.
**Key concepts**: Workflow definition, Activity definition, Worker, Client
**Complexity**: Minimal

### hello-world-js
**Description**: Same as hello-world but in plain JavaScript (no TypeScript).
**Use when**: You prefer JavaScript over TypeScript.
**Key concepts**: Workflow, Activity, Worker, Client (JS)
**Complexity**: Minimal

### hello-world-mtls
**Description**: Hello World with mTLS for connecting to Temporal Cloud.
**Use when**: You need to connect to Temporal Cloud with mutual TLS certificates.
**Key concepts**: mTLS, Temporal Cloud, TLS connection options
**Complexity**: Low

### fetch-esm
**Description**: Pure ES Modules (ESM) configuration with TypeScript.
**Use when**: You need ESM-only imports (e.g., libraries that don't support CommonJS).
**Key concepts**: ESM, tsconfig, module configuration
**Complexity**: Low

---

## Activity Patterns

### activities-examples
**Description**: Multiple Activity patterns: HTTP requests, cancellable fetch, async external completion.
**Use when**: You need to call external APIs, support cancellation, or hand off completion to an external system.
**Key concepts**: HTTP activities, `cancellationSignal`, `AsyncCompletionClient`
**Complexity**: Low

### activities-cancellation-heartbeating
**Description**: Long-running Activities with heartbeat progress reporting and cancellation support.
**Use when**: Activities take a long time and need progress tracking or graceful cancellation.
**Key concepts**: `activity.heartbeat()`, cancellation, `isCancellation()`
**Complexity**: Low

### activities-dependency-injection
**Description**: Share dependencies (DB connections, API clients) between Activity functions.
**Use when**: Multiple Activities need access to shared resources initialized once at Worker startup.
**Key concepts**: Dependency injection, Activity context, Worker factory pattern
**Complexity**: Low

### worker-specific-task-queues
**Description**: Assigns a unique task queue per Worker instance for location-aware routing.
**Use when**: Activities must run on a specific Worker (e.g., file processing where files are local).
**Key concepts**: Task queue routing, Worker identity, sticky execution
**Complexity**: Medium

---

## Workflow Patterns

### signals-queries
**Description**: Sending Signals into Workflows, querying their state, and cancellation.
**Use when**: You need to send data into a running Workflow or read its current state from outside.
**Key concepts**: `setHandler`, Signals, Queries, `condition()`, cancellation
**Complexity**: Low

### message-passing
**Description**: Comprehensive message-passing patterns including Updates, Signals, and Queries.
**Use when**: You need Updates (request/response pattern into running Workflows) or advanced messaging.
**Key concepts**: Updates, Signals, Queries, update validators, safe message handlers
**Complexity**: Medium
**Note**: Contains sub-samples — use `sample=message-passing/introduction`, `message-passing/execute-update`, or `message-passing/safe-message-handlers`

### child-workflows
**Description**: Starting Child Workflows, waiting for results, cancelling children.
**Use when**: You need to decompose a Workflow into parallel or sequential sub-Workflows.
**Key concepts**: `startChild`, `executeChild`, parent-child cancellation
**Complexity**: Low

### continue-as-new
**Description**: `continueAsNew` for Workflows that run indefinitely without growing history.
**Use when**: Your Workflow loops forever (polling, entity pattern, subscription lifecycle).
**Key concepts**: `continueAsNew`, history limits, infinite Workflows
**Complexity**: Low

### saga
**Description**: Saga pattern for compensating transactions across distributed services.
**Use when**: You need rollback/compensation logic if any step in a multi-step process fails.
**Key concepts**: Saga, compensation, try/catch/compensate, distributed transactions
**Complexity**: Medium

### mutex
**Description**: Workflows acting as distributed mutexes using Signals.
**Use when**: You need distributed locking or to serialize access to a shared resource.
**Key concepts**: Mutex, inter-Workflow Signals, `condition()`
**Complexity**: Medium

### state
**Description**: Workflow maintains state in a Map, updated and read via Signal/Query.
**Use when**: You need a stateful entity Workflow (shopping cart, game state, user session).
**Key concepts**: Workflow state, Signals to mutate, Queries to read
**Complexity**: Low

### early-return
**Description**: Return an early acknowledgment from a Workflow while it continues processing.
**Use when**: You want to confirm receipt immediately but continue background work asynchronously.
**Key concepts**: Updates, early return pattern
**Complexity**: Low

### polling
**Description**: Poll an external system until a condition is met.
**Use when**: You need to wait for an external API to reach a certain state (job completion, status checks).
**Key concepts**: Activity polling, retry, `sleep`
**Complexity**: Low

### expense
**Description**: Async Activity completion — an Activity is completed by an external HTTP call.
**Use when**: You need a human-in-the-loop or external system approval step.
**Key concepts**: Async completion, `AsyncCompletionClient`, task token
**Complexity**: Medium

### sleeping-for-days
**Description**: Workflows that sleep for very long durations (days, weeks, months).
**Use when**: You need durable long-duration delays (subscription reminders, renewal notices).
**Key concepts**: `sleep` with large durations, durable timers
**Complexity**: Low

---

## Timers and Scheduling

### timer-examples
**Description**: Timer patterns: racing Activities vs sleep, updatable timers via Signals.
**Use when**: You need timeouts, deadlines, or timers the user can extend/cancel while running.
**Key concepts**: `sleep`, `Promise.race`, `UpdatableTimer`, Signals
**Complexity**: Low

### timer-progress
**Description**: Track and report progress of a timed operation.
**Use when**: You need to show progress percentage of a long-running timed process.
**Key concepts**: `sleep`, progress queries
**Complexity**: Low

### schedules
**Description**: Schedule Workflows to run on a recurring schedule using the Schedule API.
**Use when**: You need cron-like recurring Workflow execution (hourly jobs, daily reports).
**Key concepts**: `ScheduleClient`, schedule CRUD, cron expressions
**Complexity**: Low

### cron-workflows
**Description**: *(Deprecated)* Legacy cron scheduling via Workflow options.
**Use when**: Reference only — prefer `schedules` for new projects.
**Key concepts**: `cronSchedule` option
**Complexity**: Low

---

## Nexus

### nexus-hello
**Description**: Define a Nexus Service with Operations and call them from a Workflow.
**Use when**: You need cross-namespace or cross-team Workflow orchestration via Nexus.
**Key concepts**: Nexus Service, Operation handlers, `executeNexusOperation`
**Complexity**: Medium

### nexus-cancellation
**Description**: Cancel Nexus Operations from the calling Workflow.
**Use when**: You need cancellation support in Nexus Operation calls.
**Key concepts**: Nexus cancellation, `CancellationScope`
**Complexity**: Medium

---

## Production Concerns

### production
**Description**: Pre-built Workflow bundles (Webpack) for faster Worker startup in production.
**Use when**: Worker cold-start time is a concern in production.
**Key concepts**: Webpack bundling, `bundleWorkflowCode`, production Worker setup
**Complexity**: Medium

### env-config
**Description**: TOML-based environment configuration for connecting to different Temporal clusters.
**Use when**: You need dev/staging/prod profiles with different connection settings.
**Key concepts**: `@temporalio/envconfig`, TOML profiles, environment switching
**Complexity**: Low

### patching-api
**Description**: Safely deploy breaking Workflow code changes while executions are in-flight.
**Use when**: You need to version Workflow logic for live deployments without breaking running Workflows.
**Key concepts**: `patched()`, `deprecatePatch()`, Workflow versioning
**Complexity**: Medium

### worker-versioning
**Description**: Route Workflows to specific Worker versions using Build IDs.
**Use when**: You need blue/green Worker deployments or gradual rollouts.
**Key concepts**: Build ID, Worker versioning, version sets
**Complexity**: Medium

### custom-logger
**Description**: Plug in a Winston logger for all SDK log output.
**Use when**: You need structured logging or log aggregation (Datadog, Splunk, etc.).
**Key concepts**: Custom `Runtime` logger, Winston integration
**Complexity**: Low

### interceptors-opentelemetry
**Description**: Add OpenTelemetry distributed tracing to Workflows and Activities via Interceptors.
**Use when**: You need end-to-end tracing and observability.
**Key concepts**: Interceptors, OpenTelemetry, trace propagation
**Complexity**: Medium

### sinks
**Description**: Emit metrics, logs, or alerts from inside Workflow code without side effects.
**Use when**: You need to extract data from Workflows (metrics, audit logs) that can't use Activities.
**Key concepts**: Workflow Sinks, `InjectedSinks`
**Complexity**: Medium

### vscode-debugger
**Description**: Debug Workflows step-by-step using the VS Code Temporal debugger extension.
**Use when**: You want to set breakpoints and step through Workflow code.
**Key concepts**: VS Code debugger, Workflow replay debugging
**Complexity**: Low

---

## Data Handling

### encryption
**Description**: Encrypt all Workflow payloads end-to-end with a custom Codec.
**Use when**: Payload data must be encrypted at rest and in transit (compliance, PII).
**Key concepts**: `PayloadCodec`, encryption, custom data converter
**Complexity**: Medium

### protobufs
**Description**: Use Protocol Buffers for type-safe, schema-defined Workflow data.
**Use when**: You need strong schema guarantees or protobuf compatibility with other services.
**Key concepts**: Protobuf, `PayloadConverter`, schema evolution
**Complexity**: Medium

### ejson
**Description**: Custom `PayloadConverter` using EJSON to handle rich JS types (Dates, RegExp, binary).
**Use when**: You need to pass native JS types through Temporal that standard JSON can't serialize.
**Key concepts**: `PayloadConverter`, EJSON, custom serialization
**Complexity**: Medium

### search-attributes
**Description**: Create, set, and query custom Search Attributes on Workflows.
**Use when**: You need to filter or list Workflows by custom business metadata (status, customer ID, etc.).
**Key concepts**: `upsertSearchAttributes`, typed search attributes, Workflow visibility
**Complexity**: Low

---

## Advanced Patterns

### eager-workflow-start
**Description**: Eager Workflow Start to reduce first-task latency.
**Use when**: You need the lowest possible latency from `startWorkflow` to first task execution.
**Key concepts**: Eager start, `eagerWorkflowStart` option
**Complexity**: Low

### query-subscriptions
**Description**: Subscribe to live Workflow state changes using Redis Streams and Interceptors.
**Use when**: You need real-time streaming of Workflow state to external clients.
**Key concepts**: Interceptors, Redis Streams, Immer state, subscriptions
**Complexity**: High

### dsl-interpreter
**Description**: Execute a custom YAML-defined DSL as a Temporal Workflow.
**Use when**: You want end-users to define Workflow logic via a domain-specific language.
**Key concepts**: DSL interpretation, dynamic Workflows, YAML config
**Complexity**: High

### grpc-calls
**Description**: Make raw gRPC calls to the Temporal server for operations beyond the Client API.
**Use when**: You need low-level Temporal server operations not exposed by the SDK.
**Key concepts**: gRPC, raw service calls
**Complexity**: High

---

## Full-Stack Applications

### nextjs-ecommerce-oneclick
**Description**: One-click purchase with a 5-second cancellation window. Full Next.js frontend.
**Use when**: You want a full-stack e-commerce reference with UI, timers, and cancellation.
**Key concepts**: Next.js, `sleep`, cancellation, HTTP API
**Complexity**: High

### food-delivery
**Description**: Multi-step food delivery app with Next.js frontends, tRPC, and Turborepo.
**Use when**: You want a complex full-stack app with multiple services and real-time UI.
**Key concepts**: Signals, Queries, timeouts, Next.js, tRPC, Turborepo monorepo
**Complexity**: High

### nestjs-exchange-rates
**Description**: NestJS framework integration for exchange rate Workflows.
**Use when**: You want to use Temporal inside a NestJS application.
**Key concepts**: NestJS, framework integration, dependency injection
**Complexity**: Medium

---

## AI / LLM

### ai-sdk
**Description**: Vercel AI SDK + Temporal for durable LLM Workflows (chat, tool use, MCP).
**Use when**: You're building AI agents, LLM pipelines, or MCP tool integrations.
**Key concepts**: Vercel AI SDK, OpenAI, tool use, MCP, durable AI workflows
**Complexity**: Medium
