package io.temporal.samples.hello;

import io.temporal.workflow.SignalMethod;
import io.temporal.workflow.UpdateMethod;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

@WorkflowInterface
public interface CancellationWorkflow {

  @WorkflowMethod
  String run();

  /**
   * Update handler used by the activity for faster cancellation detection.
   *
   * <p>The activity sends this update and blocks waiting for the response. When the workflow is
   * cancelled, this should return {@code cancelled=true} in the same workflow task that processes
   * the CANCEL_REQUESTED event.
   */
  @UpdateMethod
  CancellationStatus checkForWorkflowCancellation();

  @SignalMethod(name="cancel")
  void signalMockCancel();
}
