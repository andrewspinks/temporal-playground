/**
 * No-op, with the customer's real signature. It exists only so that handling a signal emits a
 * `scheduleActivity` command.
 */
export async function emitProviderQueueMetrics(_args: {
  workflowId: string;
  runningJobsCount: number;
  enqueuedJobsCount: number;
}): Promise<void> {
  // intentionally empty
}
