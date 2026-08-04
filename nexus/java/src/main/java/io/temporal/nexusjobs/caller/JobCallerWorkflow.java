package io.temporal.nexusjobs.caller;

import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/** Calls both JobService operations so their results can be compared. */
@WorkflowInterface
public interface JobCallerWorkflow {

  @WorkflowMethod
  CallerResult fetchBothWays(int todoId);
}
