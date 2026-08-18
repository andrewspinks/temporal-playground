/**
 * RECONSTRUCTION OF THE CUSTOMER'S WORKFLOW.
 *
 * Everything in this file is inferred from the three production histories -- the signal names,
 * query name and activity name are the real ones; the code shape is a guess that matches the
 * observed command patterns. Nothing here is diagnostic scaffolding, with the two exceptions
 * marked `TEST ONLY` below.
 *
 * The command tracer lives in `tracer.ts` and is NOT part of this reconstruction.
 */
import {
  condition,
  defineQuery,
  defineSignal,
  getExternalWorkflowHandle,
  proxyActivities,
  setHandler,
} from '@temporalio/workflow';
import type * as activities from './activities';

// --- Signals (names taken verbatim from the histories) -----------------------------------------

/** Enqueues a job. The customer sends this via signalWithStart, thousands per day per queue. */
export const publishToProviderQueueSignal = defineSignal<[string]>('publish_to_provider_queue');

/** Sent BY providerQueueWorkflow TO a connection workflow. This is the command that gets misordered. */
export const executeJobSignal = defineSignal<[string]>('execute_job');

/** TEST ONLY. Production entity workflows run forever; this just lets a trial end. */
export const stopSignal = defineSignal('stop');

// --- Queries -----------------------------------------------------------------------------------

/**
 * The input that is NEVER written to history. Since Aug 7 the customer sends this immediately
 * before every enqueue, so queries arrive in the same bursts as the signals.
 */
export const providerQueueJobsQuery = defineQuery<number>('provider_queue_jobs');

// --- Activities --------------------------------------------------------------------------------

const { emitProviderQueueMetrics } = proxyActivities<typeof activities>({
  startToCloseTimeout: '1 minute',
});

/** TEST ONLY knobs. Not modelling anything the customer wrote -- see `handlerHops`. */
export interface TestKnobs {
  /**
   * Number of `await`s the signal handler performs before scheduling its activity.
   *
   * This is the experimental lever, not production behaviour. It shifts the activity commands
   * later in the microtask drain relative to the dispatcher's external-signal command, which is
   * what decides where S lands among the As. See the README table.
   */
  handlerHops: number;
}

/**
 * Two independent coroutines push commands into the same Workflow Task:
 *
 *   1. each `publish_to_provider_queue` handler schedules one activity -> `scheduleActivity`      (A)
 *   2. the dispatcher, parked on `condition()`, signals a connection   -> `signalExternalWorkflow` (S)
 *
 * Neither pushes its command inline -- both travel through async interceptor chains -- so the
 * commands are emitted during the microtask drain when the SDK exits the workflow VM. Their
 * relative order is the thing that diverges on replay in production.
 *
 * No concurrency limit is modelled: `signalExternalWorkflow` only resolves once the server confirms
 * it (a later Workflow Task), so this loop already emits at most one S per task -- exactly what the
 * production histories show (ev 1398 -> 1401 -> 1402).
 */
export async function providerQueueWorkflow(
  connectionWorkflowId: string,
  test: TestKnobs = { handlerHops: 0 },
): Promise<void> {
  const queue: string[] = [];
  let stopped = false;

  setHandler(providerQueueJobsQuery, () => queue.length);
  setHandler(stopSignal, () => void (stopped = true)); // TEST ONLY

  setHandler(publishToProviderQueueSignal, async (job) => {
    queue.push(job);
    for (let i = 0; i < test.handlerHops; i++) await Promise.resolve(); // TEST ONLY
    void emitProviderQueueMetrics(queue.length); // command A, one per signal handled
  });

  // The dispatcher.
  while (!stopped) {
    await condition(() => queue.length > 0 || stopped);
    if (stopped) break;
    const job = queue.shift() as string;
    await getExternalWorkflowHandle(connectionWorkflowId).signal(executeJobSignal, job); // command S
  }
}

/**
 * Stands in for the customer's connection workflows -- the target of `execute_job`. It only needs
 * to exist and accept the signal.
 */
export async function connectionWorkflow(): Promise<void> {
  setHandler(executeJobSignal, () => {
    // the real one runs the job; here we only need a valid signal target
  });
  await condition(() => false);
}
