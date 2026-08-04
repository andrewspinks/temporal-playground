package io.temporal.nexusjobs.handler;

import io.temporal.nexusjobs.model.Todo;
import io.temporal.nexusjobs.service.TodoRequest;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/** Wrapper workflow backing the fetchTodoAsync operation. */
@WorkflowInterface
public interface FetchTodoWorkflow {

  @WorkflowMethod
  Todo fetchTodo(TodoRequest request);
}
