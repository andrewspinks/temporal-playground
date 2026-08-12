package io.temporal.samples.ndeinterleave;

/** Activities are irrelevant to the bug; they only need to produce commands and complete. */
public class OrderActivitiesImpl implements OrderActivities {

  @Override
  public void acknowledge(String idempotencyKey) {
    // no-op
  }

  @Override
  public void notifyDeadline() {
    // no-op
  }
}
