package io.temporal.nexusjobs.activities;

import io.temporal.activity.Activity;
import io.temporal.failure.ApplicationFailure;
import io.temporal.nexusjobs.model.Todo;
import io.temporal.nexusjobs.todo.TodoApi;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Wraps {@link TodoApi} as an activity, mapping its failures onto Temporal's retry model.
 *
 * <p>Compare with JobServiceImpl#fetchTodoSync, which maps the very same failures onto Nexus
 * HandlerException error types instead. Same work, two error models, because the two operations sit
 * at different layers.
 */
public class TodoActivitiesImpl implements TodoActivities {

  private static final Logger log = LoggerFactory.getLogger(TodoActivitiesImpl.class);

  private final TodoApi todoApi;

  public TodoActivitiesImpl(TodoApi todoApi) {
    this.todoApi = todoApi;
  }

  @Override
  public Todo fetchTodo(int id) {
    log.info("fetchTodo({}) attempt {}", id, Activity.getExecutionContext().getInfo().getAttempt());
    try {
      return todoApi.fetch(id);
    } catch (TodoApi.NotFound e) {
      // Retrying cannot conjure the todo into existence — fail for good.
      throw ApplicationFailure.newNonRetryableFailure(e.getMessage(), "TodoNotFound");
    } catch (TodoApi.Malformed e) {
      throw ApplicationFailure.newNonRetryableFailureWithCause(
          e.getMessage(), "TodoMalformed", e.getCause());
    } catch (TodoApi.Unavailable e) {
      // Retryable by default, so the activity's RetryOptions take over.
      throw ApplicationFailure.newFailureWithCause(
          e.getMessage(), "TodoUnavailable", e.getCause());
    }
  }
}
