package io.temporal.samples.ndeinterleave;

import io.temporal.activity.ActivityOptions;
import io.temporal.common.SearchAttributeKey;
import io.temporal.workflow.Async;
import io.temporal.workflow.Promise;
import io.temporal.workflow.Workflow;
import java.time.Duration;
import java.util.UUID;

/**
 * Two concurrent branches woken by one signal. On SDK &lt; 1.34.0 the commands they emit come out in a
 * different order during replay than during the original execution, which fails the workflow task
 * with {@code [TMPRL1100] … does not match command type …}.
 *
 * <p>Why it diverges: {@code Workflow.sideEffect} resumes its thread when the marker <b>command</b> is
 * flushed while executing, but only when the marker <b>event</b> is matched while replaying. Pre-1.34.0
 * {@code Workflow.getVersion} yields and resumes early on replay, so the deadline branch runs ahead
 * while the acknowledge branch is still parked in {@code sideEffect}. See README.md for the detail.
 *
 */
public class OrderWorkflowImpl implements OrderWorkflow {

  /**
   * Must exist in the target namespace.
   */
  static final SearchAttributeKey<String> STATUS =
      SearchAttributeKey.forKeyword("CustomKeywordField");

  private final OrderActivities activities =
      Workflow.newActivityStub(
          OrderActivities.class,
          ActivityOptions.newBuilder().setStartToCloseTimeout(Duration.ofSeconds(10)).build());

  private boolean downstreamReady;

  @Override
  public String process() {
    // Order matters: the deadline branch must be created first so that it precedes the
    // acknowledge branch in the runner's thread list. (3)
    Promise<Void> deadlineBranch = Async.procedure(this::deadlineBranch);
    Promise<Void> acknowledgeBranch = Async.procedure(this::acknowledgeBranch);

    Promise.allOf(deadlineBranch, acknowledgeBranch).get();
    return "done";
  }

  /** Emits: Version marker, Version marker, UpsertWorkflowSearchAttributes, ActivityTaskScheduled. */
  private void deadlineBranch() {
    Workflow.await(() -> downstreamReady);

    int branchVersion = Workflow.getVersion("deadline-branch", Workflow.DEFAULT_VERSION, 1);
    // The second getVersion call is essential — see (2) in the class javadoc.
    int searchAttributeVersion =
        Workflow.getVersion("deadline-search-attribute", Workflow.DEFAULT_VERSION, 1);

    if (searchAttributeVersion >= 1) {
      Workflow.upsertTypedSearchAttributes(STATUS.valueSet("DEADLINE_EXCEEDED"));
    }
    if (branchVersion >= 1) {
      activities.notifyDeadline();
    }
  }

  /** Emits: SideEffect marker, ActivityTaskScheduled. */
  private void acknowledgeBranch() {
    Workflow.await(() -> downstreamReady);

    // Resumes at command-flush time while executing, but only at marker-event time while
    // replaying. That asymmetry is the bug; it is unchanged in every SDK version to date.
    String idempotencyKey = Workflow.sideEffect(String.class, () -> UUID.randomUUID().toString());

    activities.acknowledge(idempotencyKey);
  }

  @Override
  public void downstreamReady() {
    this.downstreamReady = true;
  }
}
