/**
 * No-op. It exists only so that handling a signal emits a `scheduleActivity` command,
 * mirroring the customer's `emitProviderQueueMetrics`.
 */
export async function emitProviderQueueMetrics(_queueDepth: number): Promise<void> {
  // intentionally empty
}
