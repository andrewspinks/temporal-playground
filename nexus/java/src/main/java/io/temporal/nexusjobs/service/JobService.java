package io.temporal.nexusjobs.service;

import io.nexusrpc.Operation;
import io.nexusrpc.Service;
import io.temporal.nexusjobs.model.Todo;

/**
 * Two operations that do the same observable thing by different means, so the trade-off is visible
 * from the caller's side.
 *
 * <p>Callers cannot tell them apart from the contract alone — which is the point of Nexus. What
 * differs is the ceiling: fetchTodoSync must answer within the 10s Nexus handler deadline,
 * fetchTodoAsync has no such limit.
 */
@Service
public interface JobService {

  /** Handled inline by the Nexus worker. Bounded by the 10s sync handler deadline. */
  @Operation
  Todo fetchTodoSync(TodoRequest input);

  /** Backed by a workflow, so the caller gets a token. No 10s ceiling. */
  @Operation
  Todo fetchTodoAsync(TodoRequest input);
}
