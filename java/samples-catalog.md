# Java Temporal Samples Catalog

Catalog of samples from [temporalio/samples-java](https://github.com/temporalio/samples-java).
Used by Claude to select the best starting point for a new project.

The Java samples are organized as packages under `core/src/main/java/io/temporal/samples/`.
Each sample package may contain multiple runnable Java files — each has its own `main` method.

> To see what's currently in the cache: `ls .cache/samples-java/core/src/main/java/io/temporal/samples/`

---

## Basic / Getting Started

### hello
**Description**: Suite of 30+ minimal examples covering the full breadth of Temporal Java SDK features.
**Use when**: Starting from scratch, learning any core concept, or you need a clean simple template.
**Key files**: `HelloActivity.java`, `HelloSignal.java`, `HelloQuery.java`, `HelloUpdate.java`, `HelloChild.java`, `HelloAsync.java`, `HelloSchedules.java`, `HelloCancellationScope.java`, and many more.
**Key concepts**: Workflow, Activity, Worker, Client, Signals, Queries, Updates, Child Workflows, Timers, Schedules
**Complexity**: Minimal
**Run**: `./gradlew run -PmainClass=io.temporal.samples.hello.HelloActivity`

---

## Scenario-Based Samples

### moneytransfer
**Description**: End-to-end money transfer workflow — withdraw, deposit, with error handling.
**Use when**: You want a realistic multi-step business workflow example with activity sequencing.
**Key concepts**: Sequential Activities, error handling, compensation
**Complexity**: Low
**Run**: `./gradlew run -PmainClass=io.temporal.samples.moneytransfer.TransferApp`

### bookingsaga
**Description**: Saga pattern for booking a trip (car, hotel, flight) with compensation on failure.
**Use when**: You need distributed transaction rollback across multiple services.
**Key concepts**: Saga, compensation, try/catch/compensate
**Complexity**: Medium
**Run**: `./gradlew run -PmainClass=io.temporal.samples.bookingsaga.TripBookingApp`

### bookingsyncsaga
**Description**: Synchronous variant of the booking saga — returns result directly to caller.
**Use when**: You need saga with synchronous result delivery.
**Key concepts**: Saga, synchronous result, Updates
**Complexity**: Medium

### fileprocessing
**Description**: Processes files using Worker-affinity routing — Activities run on specific Workers.
**Use when**: File or resource processing that must happen on the same machine that downloaded it.
**Key concepts**: Task queue routing, Worker affinity, sticky execution, heartbeating
**Complexity**: Medium

### moneybatch
**Description**: Batch payment processing with parent/child workflow decomposition.
**Use when**: You need to process a large list of items in parallel child workflows.
**Key concepts**: Child Workflows, parallel execution, batch processing
**Complexity**: Medium

---

## Workflow Patterns

### polling
**Description**: Poll an external system until a condition is met.
**Use when**: You need to wait for an external API to reach a certain state.
**Key concepts**: Activity polling, retry, sleep
**Complexity**: Low

### earlyreturn
**Description**: Return an early result from a Workflow via Update while it continues running.
**Use when**: You want to acknowledge receipt immediately but continue background work.
**Key concepts**: Updates, early return pattern
**Complexity**: Low

### safemessagepassing
**Description**: Safe Signal and Update handling with mutex patterns to avoid race conditions.
**Use when**: Multiple concurrent signals/updates modify the same workflow state.
**Key concepts**: Signals, Updates, mutex, safe message handlers
**Complexity**: Medium

### sleepfordays
**Description**: Workflows that sleep for very long durations (days, weeks, months).
**Use when**: You need durable long-duration delays (subscription reminders, renewal notices).
**Key concepts**: `Workflow.sleep()`, durable timers
**Complexity**: Low

### updatabletimer
**Description**: A timer that can be extended or shortened via Signals while it's running.
**Use when**: You need a cancellable or adjustable timer inside a Workflow.
**Key concepts**: Signals, dynamic sleep, timer management
**Complexity**: Low

### asyncchild
**Description**: Start child workflows asynchronously and handle their results.
**Use when**: You need fire-and-forget child execution with optional result handling.
**Key concepts**: `Async.function`, child workflows, `Promise`
**Complexity**: Low

### asyncuntypedchild
**Description**: Start untyped child workflows dynamically using string workflow type names.
**Use when**: You need to invoke workflows by name without compile-time type binding.
**Key concepts**: `UntypedWorkflowStub`, dynamic invocation
**Complexity**: Low

### getresultsasync
**Description**: Get the result of a running workflow from outside without blocking the caller.
**Use when**: You start a workflow and want to retrieve its result later from a different process.
**Key concepts**: `WorkflowClient.newUntypedWorkflowStub`, async result polling
**Complexity**: Low

### dsl
**Description**: Execute a YAML-defined DSL as a Temporal Workflow.
**Use when**: You want end-users to define workflow logic via a domain-specific language.
**Key concepts**: DSL interpretation, dynamic workflows, YAML config
**Complexity**: High

---

## Timers and Scheduling

### hello (HelloSchedules.java)
**Description**: Schedule workflows to run on a recurring schedule using the Schedule API.
**Use when**: You need cron-like recurring workflow execution.
**Key concepts**: `ScheduleClient`, schedule CRUD, cron expressions
**Complexity**: Low
**Run**: `./gradlew run -PmainClass=io.temporal.samples.hello.HelloSchedules`

### hello (HelloCron.java)
**Description**: *(Deprecated)* Legacy cron scheduling via Workflow options.
**Use when**: Reference only — prefer `HelloSchedules` for new projects.
**Key concepts**: `setCronSchedule` option
**Complexity**: Low

---

## Nexus

### nexus
**Description**: Define a Nexus Service with Operations and call them from a Workflow.
**Use when**: You need cross-namespace or cross-team Workflow orchestration via Nexus.
**Key concepts**: Nexus Service, Operation handlers, `executeNexusOperation`
**Complexity**: Medium

### nexuscancellation
**Description**: Cancel Nexus Operations from the calling Workflow.
**Use when**: You need cancellation support in Nexus Operation calls.
**Key concepts**: Nexus cancellation
**Complexity**: Medium

### nexuscontextpropagation
**Description**: Propagate context (headers, auth) through Nexus Operation calls.
**Use when**: You need to pass contextual data through cross-namespace calls.
**Key concepts**: Nexus, context propagation, headers
**Complexity**: Medium

### nexusmultipleargs
**Description**: Call Nexus Operations with multiple arguments.
**Use when**: Your Nexus Operations require more than one input parameter.
**Key concepts**: Nexus, multi-argument operations
**Complexity**: Low

---

## Observability & Infrastructure

### metrics
**Description**: Emit Temporal SDK metrics via Micrometer and Prometheus.
**Use when**: You need Worker and SDK-level metrics for monitoring dashboards.
**Key concepts**: Micrometer, Prometheus, Worker metrics
**Complexity**: Low

### tracing
**Description**: Distributed tracing with OpenTelemetry and Jaeger.
**Use when**: You need end-to-end trace propagation across Workflows and Activities.
**Key concepts**: OpenTelemetry, Jaeger, trace propagation, interceptors
**Complexity**: Medium

### ssl
**Description**: Connect to Temporal Cloud or a TLS-secured cluster using mTLS certificates.
**Use when**: You need to connect to Temporal Cloud with mutual TLS.
**Key concepts**: mTLS, TLS configuration, Temporal Cloud
**Complexity**: Low

### encryptedpayloads
**Description**: Encrypt all Workflow payloads with a custom `PayloadCodec`.
**Use when**: Payload data must be encrypted at rest and in transit.
**Key concepts**: `PayloadCodec`, encryption, custom data converter
**Complexity**: Medium

### encodefailures
**Description**: Encode exception details in workflow failures to avoid leaking sensitive info.
**Use when**: You need to prevent exception stack traces from being stored in plain text.
**Key concepts**: Failure encoding, `DataConverter`
**Complexity**: Low

### payloadconverter
**Description**: Custom `PayloadConverter` for non-standard serialization formats.
**Use when**: You need to pass custom types through Temporal that the default JSON converter can't handle.
**Key concepts**: `PayloadConverter`, custom serialization
**Complexity**: Medium

---

## Advanced Patterns

### countinterceptor
**Description**: Custom Workflow and Activity interceptors that count invocations.
**Use when**: You need to instrument or intercept Workflow/Activity execution for custom logic.
**Key concepts**: Interceptors, `WorkflowInboundCallsInterceptor`, `ActivityInboundCallsInterceptor`
**Complexity**: Medium

### retryonsignalinterceptor
**Description**: Interceptor that retries failed Activities on a Signal instead of immediately.
**Use when**: You want human-in-the-loop retry approval for failed activities.
**Key concepts**: Interceptors, Signals, custom retry logic
**Complexity**: Medium

### excludefrominterceptor
**Description**: Selectively exclude certain Workflows or Activities from interceptor logic.
**Use when**: You have an interceptor but need to opt specific workflows out.
**Key concepts**: Interceptors, custom annotations, conditional execution
**Complexity**: Medium

### customannotation
**Description**: Define custom Java annotations to control Workflow/Activity behavior.
**Use when**: You need declarative configuration of Temporal options via annotations.
**Key concepts**: Custom annotations, reflection, `WorkflowImplementationOptions`
**Complexity**: Medium

### customchangeversion
**Description**: Custom workflow versioning strategy beyond the built-in `getVersion()` API.
**Use when**: You need fine-grained control over how workflow code changes are versioned.
**Key concepts**: Workflow versioning, `getVersion()`, migration
**Complexity**: High

### workerversioning
**Description**: Route Workflows to specific Worker versions using Build IDs.
**Use when**: You need blue/green Worker deployments or gradual rollouts.
**Key concepts**: Build ID, Worker versioning
**Complexity**: Medium

### terminateworkflow
**Description**: Programmatically terminate a running Workflow from outside.
**Use when**: You need to forcibly stop a workflow that can't be cancelled gracefully.
**Key concepts**: `WorkflowStub.terminate()`, forced termination
**Complexity**: Low

### listworkflows
**Description**: List and filter Workflows by status and search attributes.
**Use when**: You need to query or enumerate running/completed workflows programmatically.
**Key concepts**: `WorkflowClient.listExecutions()`, workflow visibility, filters
**Complexity**: Low

### batch
**Description**: Process a large dataset in parallel using child workflows and signals.
**Use when**: You need to fan out work across thousands of items with progress tracking.
**Key concepts**: Child Workflows, Signals for control, parallel processing
**Complexity**: High

### peractivityoptions
**Description**: Set different retry policies and timeouts on a per-activity basis.
**Use when**: Different activities in the same workflow have different reliability requirements.
**Key concepts**: `ActivityOptions`, per-activity config, retry policies
**Complexity**: Low

### autoheartbeat
**Description**: Automatically heartbeat long-running Activities without manual calls.
**Use when**: You have long-running Activities that need heartbeating but don't control the code.
**Key concepts**: Auto-heartbeat, `ActivityOptions`, heartbeat timeout
**Complexity**: Low

### envconfig
**Description**: Configure Temporal client via environment variables and TOML config files.
**Use when**: You need dev/staging/prod profiles with different connection settings.
**Key concepts**: `ClientConfigProfile`, env vars, TOML config
**Complexity**: Low

### apikey
**Description**: Authenticate with Temporal Cloud using API keys.
**Use when**: You need to connect to Temporal Cloud with an API key instead of mTLS.
**Key concepts**: API key authentication, Temporal Cloud, gRPC metadata
**Complexity**: Low

### packetdelivery
**Description**: Multi-step package delivery workflow with status tracking.
**Use when**: You want a realistic logistics/delivery workflow with state tracking and signals.
**Key concepts**: Signals, Queries, multi-step workflow, state machine
**Complexity**: Medium
