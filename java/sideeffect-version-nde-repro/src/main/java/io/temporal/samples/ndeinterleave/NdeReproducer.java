package io.temporal.samples.ndeinterleave;

import io.temporal.api.enums.v1.EventType;
import io.temporal.api.enums.v1.WorkflowTaskFailedCause;
import io.temporal.api.history.v1.HistoryEvent;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.client.WorkflowOptions;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.serviceclient.WorkflowServiceStubsOptions;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;
import io.temporal.worker.WorkerOptions;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * Runs {@link OrderWorkflow} with the sticky cache disabled, so every workflow task arrives as a full
 * replay. On SDK 1.33.0 that replay disagrees with the original execution, the workflow task fails
 * with {@code [TMPRL1100]} and the execution is stuck for good. On 1.34.0+ the same code completes.
 *
 * <pre>
 *   mise run repro-old    # SDK 1.33.0 -&gt; stuck
 *   mise run repro-new    # SDK 1.36.1 -&gt; completes
 * </pre>
 */
public final class NdeReproducer {

  private static final String TARGET = envOr("TEMPORAL_ADDRESS", "localhost:7233");
  private static final String NAMESPACE = envOr("TEMPORAL_NAMESPACE", "default");
  private static final String SDK_VERSION = System.getProperty("repro.sdkVersion", "unknown");

  public static void main(String[] args) throws Exception {
    WorkflowServiceStubs service =
        WorkflowServiceStubs.newServiceStubs(
            WorkflowServiceStubsOptions.newBuilder().setTarget(TARGET).build());
    WorkflowClient client =
        WorkflowClient.newInstance(
            service, WorkflowClientOptions.newBuilder().setNamespace(NAMESPACE).build());

    System.out.println();
    System.out.println("══ sideEffect + getVersion replay-ordering NDE ══");
    System.out.printf("   temporal-sdk %s   %s/%s%n", SDK_VERSION, TARGET, NAMESPACE);

    try {
      String id = "nde-repro-" + shortUuid();
      System.out.println();
      System.out.printf("   workflow id ......... %s%n", id);

      WorkerFactory factory = WorkerFactory.newInstance(client);
      // Every workflow task has to arrive as a full replay — that is what exposes the bug. With a
      // warm sticky cache the commands are matched in the order they were emitted and the run stays
      // green, which is why this looks intermittent in production.
      // Duration.ZERO expires the sticky task immediately, so full history is redelivered on the
      // normal queue. Note setWorkflowCacheSize(0) does NOT work for this: <= 0 means "use default".
      Worker worker =
              factory.newWorker(
                      id, WorkerOptions.newBuilder().setStickyQueueScheduleToStartTimeout(Duration.ZERO).build());
      worker.registerWorkflowImplementationTypes(OrderWorkflowImpl.class);
      worker.registerActivitiesImplementations(new OrderActivitiesImpl());
      factory.start();

      try {
        OrderWorkflow stub = newStub(client, id);
        WorkflowClient.start(stub::process);
        awaitFirstWorkflowTask(client, id);
        stub.downstreamReady(); // send signal
        awaitNonDeterminismFailure(client, id);
      } finally {
        factory.shutdownNow();
        factory.awaitTermination(5, TimeUnit.SECONDS);
      }
    } finally {
      service.shutdownNow();
      service.awaitTermination(5, TimeUnit.SECONDS);
    }
  }

  private static OrderWorkflow newStub(WorkflowClient client, String id) {
    return client.newWorkflowStub(
        OrderWorkflow.class,
        WorkflowOptions.newBuilder()
            .setTaskQueue(id) // a task queue per run, so a stale worker cannot pick these up
            .setWorkflowId(id)
            .setWorkflowExecutionTimeout(Duration.ofMinutes(5))
            .build());
  }

  /**
   * Waits until the workflow has parked on its two awaits, so the signal lands in its own workflow
   * task rather than being folded into the first one.
   */
  private static void awaitFirstWorkflowTask(WorkflowClient client, String id) throws Exception {
    long deadline = System.currentTimeMillis() + 15_000;
    while (System.currentTimeMillis() < deadline) {
      try {
        boolean done =
            client.fetchHistory(id).getEvents().stream()
                .anyMatch(e -> e.getEventType() == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED);
        if (done) {
          return;
        }
      } catch (RuntimeException ignored) {
        // history not available yet
      }
      Thread.sleep(50);
    }
    throw new IllegalStateException("workflow " + id + " never completed its first workflow task");
  }


  /**
   * Keeps the worker alive until the workflow task fails on non-determinism, and prints it. On SDK
   * 1.34.0+ that never happens: the workflow just completes.
   */
  private static void awaitNonDeterminismFailure(WorkflowClient client, String id) throws Exception {
    long deadline = System.currentTimeMillis() + 30_000;
    while (System.currentTimeMillis() < deadline) {
      for (HistoryEvent e : client.fetchHistory(id).getEvents()) {
        if (e.getEventType() == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED
            && e.getWorkflowTaskFailedEventAttributes().getCause()
                == WorkflowTaskFailedCause.WORKFLOW_TASK_FAILED_CAUSE_NON_DETERMINISTIC_ERROR) {
          System.out.printf("   NDE reproduced ...... event %d WORKFLOW_TASK_FAILED%n", e.getEventId());
          System.out.printf(
              "       %s%n", e.getWorkflowTaskFailedEventAttributes().getFailure().getMessage());
          System.out.println();
          System.out.println("   The workflow is stuck: this task retries forever. Inspect it in the");
          System.out.println("   Web UI, then clean up with:");
          System.out.printf(
              "       temporal workflow terminate --workflow-id %s --namespace %s%n", id, NAMESPACE);
          return;
        }
        if (e.getEventType() == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED) {
          System.out.println("   no NDE .............. the workflow completed cleanly");
          System.out.println("   Expected on SDK 1.34.0+: getVersion no longer yields, so the two");
          System.out.println("   branches cannot interleave (PR #2819).");
          return;
        }
      }
      Thread.sleep(500);
    }
    System.out.println("   neither an NDE nor a completion within 30s (unexpected)");
  }

  private static String shortUuid() {
    return UUID.randomUUID().toString().substring(0, 8);
  }

  private static String envOr(String name, String fallback) {
    String value = System.getenv(name);
    return value == null || value.isEmpty() ? fallback : value;
  }

  private NdeReproducer() {}
}
