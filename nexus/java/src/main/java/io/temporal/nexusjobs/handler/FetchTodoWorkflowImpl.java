package io.temporal.nexusjobs.handler;

import io.temporal.activity.ActivityOptions;
import io.temporal.common.RetryOptions;
import io.temporal.nexusjobs.activities.TodoActivities;
import io.temporal.nexusjobs.model.Todo;
import io.temporal.nexusjobs.service.TodoRequest;
import io.temporal.workflow.Workflow;
import java.time.Duration;

/**
 * The workflow behind the async Nexus operation.
 *
 * <p>Trivial on purpose — the point is that being a workflow removes the sync operation's 10s ceiling
 * and turns the work into a durable, inspectable execution. Retries, timers, child workflows, signals
 * and continue-as-new are all available here; none of them exist in a sync handler.
 *
 * <p>The activity stub sets no task queue, so it inherits the workflow's — the same queue
 * NexusHandlerWorker registers the activity on.
 */
public class FetchTodoWorkflowImpl implements FetchTodoWorkflow {

  private final TodoActivities activities =
      Workflow.newActivityStub(
          TodoActivities.class,
          ActivityOptions.newBuilder()
              .setStartToCloseTimeout(Duration.ofSeconds(10))
              .setRetryOptions(RetryOptions.newBuilder().setMaximumAttempts(3).build())
              .build());

  @Override
  public Todo fetchTodo(TodoRequest request) {
    return activities.fetchTodo(request.getId());
  }
}
