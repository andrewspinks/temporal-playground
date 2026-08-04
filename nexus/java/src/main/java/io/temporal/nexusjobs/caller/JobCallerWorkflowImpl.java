package io.temporal.nexusjobs.caller;

import io.temporal.nexusjobs.Config;
import io.temporal.nexusjobs.model.Todo;
import io.temporal.nexusjobs.service.JobService;
import io.temporal.nexusjobs.service.TodoRequest;
import io.temporal.workflow.NexusOperationHandle;
import io.temporal.workflow.NexusOperationOptions;
import io.temporal.workflow.NexusServiceOptions;
import io.temporal.workflow.Workflow;
import java.time.Duration;

public class JobCallerWorkflowImpl implements JobCallerWorkflow {

  /**
   * The endpoint is set here on the stub. It can also be supplied at worker registration via
   * WorkflowImplementationOptions#setNexusServiceOptions, which keeps the endpoint name out of
   * workflow code — see CallerWorker for that alternative.
   */
  private final JobService jobService =
      Workflow.newNexusServiceStub(
          JobService.class,
          NexusServiceOptions.newBuilder()
              .setEndpoint(Config.NEXUS_ENDPOINT)
              .setOperationOptions(
                  NexusOperationOptions.newBuilder()
                      // Applies to both operations. The sync one is additionally capped by the
                      // handler-side 10s deadline, which this cannot extend.
                      .setScheduleToCloseTimeout(Duration.ofSeconds(30))
                      .build())
              .build());

  @Override
  public CallerResult fetchBothWays(int todoId) {
    TodoRequest request = new TodoRequest(todoId);

    // Calling the stub method directly blocks until the operation completes.
    long t0 = Workflow.currentTimeMillis();
    Todo viaSyncOperation = jobService.fetchTodoSync(request);
    long t1 = Workflow.currentTimeMillis();

    // startNexusOperation hands back a handle instead, so the operation's start and its result can
    // be awaited separately.
    NexusOperationHandle<Todo> handle =
        Workflow.startNexusOperation(jobService::fetchTodoAsync, request);
    // Resolves once the operation has started. For a workflow-backed operation the resulting
    // NexusOperationExecution carries the operation token, which is what a caller would keep in
    // order to cancel it later.
    handle.getExecution().get();
    Todo viaAsyncOperation = handle.getResult().get();
    long t2 = Workflow.currentTimeMillis();

    return new CallerResult(viaSyncOperation, viaAsyncOperation, t1 - t0, t2 - t1);
  }
}
