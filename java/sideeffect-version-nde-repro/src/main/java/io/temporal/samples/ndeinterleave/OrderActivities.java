package io.temporal.samples.ndeinterleave;

import io.temporal.activity.ActivityInterface;

@ActivityInterface
public interface OrderActivities {

  /** Called by the acknowledge branch, after its {@code Workflow.sideEffect}. */
  void acknowledge(String idempotencyKey);

  /** Called by the deadline branch, after its search-attribute upsert. */
  void notifyDeadline();
}
