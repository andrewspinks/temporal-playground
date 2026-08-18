/**
 * PORT OF THE CUSTOMER'S WORKFLOW.
 *
 * Close port of `playground/ts/customer-nde/workflow-source/self-contained-copy.ts`, which is a
 * faithful inline of their production source. Signal, query and activity names are the real ones.
 * Only our naming convention differs, plus the deliberate omissions noted below.
 *
 * Not ported, to keep the repro small: all `log.info` calls, the `continueAsNew` tail, luxon
 * (the millisecond literals are already inlined), and the activity timeouts other than
 * startToCloseTimeout. None of them can affect the order commands are pushed in.
 *
 * The command tracer lives in `tracer.ts` and is NOT part of this port.
 */
import {
  condition,
  defineQuery,
  defineSignal,
  getExternalWorkflowHandle,
  patched,
  proxyActivities,
  setHandler,
  sleep,
  workflowInfo,
} from '@temporalio/workflow';
import type * as activities from './activities';

export type ProviderQueueSignal = {
  jobId: string;
  entityWorkflowId: string;
  maxConcurrentJobs: number;
  isPriority?: boolean;
};
export type JobCompleteSignal = { jobId: string };

export type ProviderQueueArgs = {
  maxConcurrentJobs: number;
  publishQueue?: ProviderQueueSignal[];
  runningJobs: string[];
};

// --- Signals (names verbatim from the customer's constants) ------------------------------------

export const publishToProviderQueueSignal = defineSignal<[ProviderQueueSignal]>('publish_to_provider_queue');
export const priorityPublishToProviderQueueSignal = defineSignal<[ProviderQueueSignal]>(
  'priority_publish_to_provider_queue',
);
export const jobCompletedSignal = defineSignal<[JobCompleteSignal]>('job_completed');
export const jobFailedSignal = defineSignal<[JobCompleteSignal]>('job_failed');

/** Sent BY providerQueueWorkflow TO an entity workflow. This is the command that gets misordered. */
export const executeJobSignal = defineSignal<[{ jobId: string }]>('execute_job');

// --- Query ---------------------------------------------------------------------------------------

/**
 * The input that is NEVER written to history. Since Aug 7 the customer runs this depth check
 * immediately before every enqueue signalWithStart.
 */
export const providerQueueJobsQuery = defineQuery('provider_queue_jobs');

const EMIT_PROVIDER_QUEUE_METRICS = 'emit-provider-queue-metrics';
const EXECUTE_JOB = 'execute_job';

const { emitProviderQueueMetrics } = proxyActivities<typeof activities>({
  startToCloseTimeout: 28_800_000, // 8h, as in production
  retry: { maximumAttempts: 8 },
});

/**
 * Three command sources feed the same Workflow Task:
 *
 *   1. each publish handler schedules a metrics activity            -> `scheduleActivity`       (A)
 *   2. each job_completed / job_failed handler does the same        -> `scheduleActivity`       (A)
 *   3. the dispatcher, parked on `condition()`, signals an entity   -> `signalExternalWorkflow` (S)
 *      and then schedules a metrics activity of its own             -> `scheduleActivity`       (A)
 *
 * `scheduleActivity` is pushed synchronously at call time, so within a single activation every
 * handler's A is pushed during the synchronous job loop and S can only follow in the microtask
 * drain -- S is necessarily last. The corrupted production tasks recorded S mid-batch, which means
 * those Workflow Tasks were delivered as more than one activation. See the plan/README.
 */
export async function providerQueueWorkflow({
  maxConcurrentJobs,
  publishQueue = [],
  runningJobs = [],
}: ProviderQueueArgs): Promise<void> {
  let maximumConcurrentJobs = maxConcurrentJobs;

  const queueSignalHandler = (isPriority: boolean) => {
    return async (args: ProviderQueueSignal) => {
      // Customer writes this as a ternary expression statement; if/else is identical and
      // keeps eslint's no-unused-expressions happy.
      if (isPriority) publishQueue.unshift({ ...args, isPriority });
      else publishQueue.push({ ...args, isPriority });

      maximumConcurrentJobs = args.maxConcurrentJobs;

      if (patched(EMIT_PROVIDER_QUEUE_METRICS)) {
        await emitProviderQueueMetrics({
          workflowId: workflowInfo().workflowId,
          runningJobsCount: runningJobs.length,
          enqueuedJobsCount: publishQueue.length,
        }).catch(() => undefined);
      }
    };
  };

  setHandler(publishToProviderQueueSignal, queueSignalHandler(false));
  setHandler(priorityPublishToProviderQueueSignal, queueSignalHandler(true));

  const removeFromRunningJobs = () => async (signal: JobCompleteSignal) => {
    const index = runningJobs.indexOf(signal.jobId);
    if (index > -1) {
      runningJobs.splice(index, 1);

      if (patched(EMIT_PROVIDER_QUEUE_METRICS)) {
        await emitProviderQueueMetrics({
          workflowId: workflowInfo().workflowId,
          runningJobsCount: runningJobs.length,
          enqueuedJobsCount: publishQueue.length,
        }).catch(() => undefined);
      }
    }
  };

  setHandler(jobCompletedSignal, removeFromRunningJobs());
  setHandler(jobFailedSignal, removeFromRunningJobs());

  setHandler(providerQueueJobsQuery, () => ({
    maxConcurrentJobs,
    runningJobs,
    runningJobsCount: runningJobs.length,
    publishQueueJobs: publishQueue.map((job) => job.jobId),
    publishQueueCount: publishQueue.length,
  }));

  while (!workflowInfo().continueAsNewSuggested) {
    await condition(() => shouldProcessNextJob({ publishQueue, runningJobs, maximumConcurrentJobs }));

    if (publishQueue.length === 0) break;

    const next = publishQueue.shift();
    if (!next) continue;

    const { jobId, entityWorkflowId } = next;

    try {
      const handle = getExternalWorkflowHandle(entityWorkflowId);
      await handle.signal(EXECUTE_JOB, { jobId }); // command S
      // NOTE: this runs only once the external signal resolves, i.e. in a LATER Workflow Task.
      // That is why runningJobsCount is unchanged across the whole of a corrupted task.
      runningJobs.push(jobId);

      if (patched(EMIT_PROVIDER_QUEUE_METRICS)) {
        await emitProviderQueueMetrics({
          workflowId: workflowInfo().workflowId,
          runningJobsCount: runningJobs.length,
          enqueuedJobsCount: publishQueue.length,
        }).catch(() => undefined);
      }
    } catch {
      // production logs and carries on
    }
  }
}

/**
 * Verbatim from the customer. The second clause matters: when nothing is queued and nothing is
 * running the condition is true, the loop breaks and the workflow ends -- which is how a trial
 * finishes without needing a synthetic stop signal.
 */
function shouldProcessNextJob({
  publishQueue,
  runningJobs,
  maximumConcurrentJobs,
}: {
  publishQueue: ProviderQueueSignal[];
  runningJobs: string[];
  maximumConcurrentJobs: number;
}): boolean {
  return (
    (publishQueue.length > 0 && runningJobs.length < maximumConcurrentJobs) ||
    (publishQueue.length === 0 && runningJobs.length === 0)
  );
}

/** The customer's `entityStub`: receives `execute_job`. */
export async function entityWorkflow(): Promise<void> {
  setHandler(executeJobSignal, () => {
    // the real one runs the job
  });
  await sleep(7_200_000);
}
