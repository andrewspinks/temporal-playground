package io.temporal.samples.ndeinterleave;

import io.temporal.workflow.SignalMethod;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

@WorkflowInterface
public interface OrderWorkflow {

  @WorkflowMethod
  String process();

  /**
   * A single signal that unblocks BOTH branches. One history event means both workflow threads
   * become runnable inside the same workflow task, which is the condition this repro needs.
   */
  @SignalMethod
  void downstreamReady();
}
