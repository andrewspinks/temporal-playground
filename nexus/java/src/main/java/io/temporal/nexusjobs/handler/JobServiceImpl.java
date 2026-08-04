package io.temporal.nexusjobs.handler;

import io.nexusrpc.handler.HandlerException;
import io.nexusrpc.handler.OperationHandler;
import io.nexusrpc.handler.OperationImpl;
import io.nexusrpc.handler.ServiceImpl;
import io.temporal.client.WorkflowOptions;
import io.temporal.nexus.Nexus;
import io.temporal.nexus.WorkflowRunOperation;
import io.temporal.nexusjobs.model.Todo;
import io.temporal.nexusjobs.service.JobService;
import io.temporal.nexusjobs.service.TodoRequest;
import io.temporal.nexusjobs.todo.TodoApi;

/**
 * The two kinds of Nexus operation, side by side.
 *
 * <p>A caller cannot tell them apart from the contract — that is the point of Nexus. What differs is
 * what the handler does with the request, and how long it may take.
 */
@ServiceImpl(service = JobService.class)
public class JobServiceImpl {

  private final TodoApi todoApi;

  /** Injected so a handler test can pass a fake instead of hitting the network. */
  public JobServiceImpl(TodoApi todoApi) {
    this.todoApi = todoApi;
  }

  /**
   * A synchronous operation: the handler does the work inline and returns the result.
   *
   * <p>A sync handler is ordinary code — free to call out to services, query a database, or compute
   * something. There is no workflow and no event history behind it.
   *
   * <p>The catch is the deadline. Sync operations must complete within a fixed <b>10 seconds</b>,
   * measured from the caller's side. Handlers that overrun are retried until the operation's
   * schedule-to-close expires, so slow work here turns into repeated work rather than a slow success.
   * Anything whose latency is not predictably small belongs in the workflow-backed operation below.
   */
  @OperationImpl
  public OperationHandler<TodoRequest, Todo> fetchTodoSync() {
    return OperationHandler.sync(
        (ctx, details, input) -> {
          try {
            return todoApi.fetch(input.getId());
          } catch (TodoApi.NotFound e) {
            // NOT_FOUND is non-retryable by default, so the caller fails fast instead of burning
            // its schedule-to-close on an id that will never exist.
            //
            // Passing the message explicitly avoids the "handler error: " prefix the
            // (ErrorType, Throwable) constructor adds.
            throw new HandlerException(HandlerException.ErrorType.NOT_FOUND, e.getMessage(), e);
          } catch (TodoApi.Malformed e) {
            // INTERNAL is retryable by default; this will not improve, so say so explicitly.
            throw new HandlerException(
                HandlerException.ErrorType.INTERNAL,
                e.getMessage(),
                e,
                HandlerException.RetryBehavior.NON_RETRYABLE);
          } catch (TodoApi.Unavailable e) {
            // UNAVAILABLE is retryable — the Nexus machinery will try again until the caller's
            // schedule-to-close runs out.
            throw new HandlerException(
                HandlerException.ErrorType.UNAVAILABLE, e.getMessage(), e);
          }
        });
  }

  /**
   * An asynchronous operation, backed by a workflow.
   *
   * <p>The operation completes as soon as {@link FetchTodoWorkflow} <em>starts</em>. The caller is
   * handed an operation token, and Temporal delivers the eventual result through the operation's
   * callback. No 10s ceiling, and the work becomes a durable execution the handler namespace can be
   * inspected for, reset, or cancelled.
   *
   * <p>{@code WorkflowRunOperation.fromWorkflowMethod} is the shortest way to expose a workflow. For
   * an operation whose input differs from the workflow's, or to use an untyped stub, reach for
   * {@code WorkflowRunOperation.fromWorkflowHandle}.
   */
  @OperationImpl
  public OperationHandler<TodoRequest, Todo> fetchTodoAsync() {
    return WorkflowRunOperation.fromWorkflowMethod(
        (ctx, details, input) ->
            Nexus.getOperationContext()
                    .getWorkflowClient()
                    .newWorkflowStub(
                        FetchTodoWorkflow.class,
                        // Workflow IDs should be business-meaningful. Tying it to the todo also
                        // dedupes concurrent requests for the same one onto a single workflow.
                        //
                        // Task queue defaults to the queue this operation is handled on.
                        WorkflowOptions.newBuilder()
                            .setWorkflowId("fetch-todo-" + input.getId())
                            .build())
                ::fetchTodo);
  }
}
