/**
 * The starter. Runs the experiment in three phases:
 *
 *   1. start one entityWorkflow -- the target for `execute_job`
 *   2. run ATTEMPTS independent trials; each drives a fresh providerQueueWorkflow to completion and
 *      captures its history
 *   3. replay every captured history against the very same workflow code
 *
 * A history that will not replay is the bug: same code, same SDK, its own history.
 */
import { mkdirSync, writeFileSync } from 'fs';
import * as path from 'path';
import { Client, Connection, type WorkflowHandle } from '@temporalio/client';
import { historyToJSON } from '@temporalio/common/lib/proto-utils';
import { Worker } from '@temporalio/worker';
import { ADDRESS, NAMESPACE, TASK_QUEUE } from './shared';
import {
  entityWorkflow,
  jobCompletedSignal,
  providerQueueJobsQuery,
  providerQueueWorkflow,
  publishToProviderQueueSignal,
} from './workflows';

type History = Parameters<typeof historyToJSON>[0];
type Trial = { workflowId: string; history: History };

/** QUERIES=off is the control arm: identical run with the unrecorded input removed. */
const QUERIES = process.env.QUERIES !== 'off';
/** Enqueues per burst. Needs to be big enough that several land in one Workflow Task. */
const JOBS = Number(process.env.JOBS ?? 12);
/** Independent trials. */
const ATTEMPTS = Number(process.env.ATTEMPTS ?? 25);
/** Concurrent queriers, modelling the customer's many parallel producers. */
const QUERIERS = Number(process.env.QUERIERS ?? 6);
/** High enough that the whole burst can dispatch without waiting on job_completed. */
const MAX_CONCURRENT = Number(process.env.MAX_CONCURRENT ?? JOBS);

const HISTORY_DIR = path.resolve(__dirname, '../../../histories');
const OUT_FILE = path.join(HISTORY_DIR, 'nde-query-ordering-1.16.1.json');

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * The Aug 7 traffic pattern: a depth-check query immediately before every enqueue signalWithStart,
 * from many producers at once.
 *
 * Modelled as a query storm running alongside a tight burst of signalWithStart calls rather than
 * `await query(); await signalWithStart()` per job -- serialising it that way spaces the enqueues
 * out, and we would never get several signals into one Workflow Task, which is the precondition
 * for the bug.
 */
async function burstEnqueuesWhileQuerying(
  client: Client,
  workflowId: string,
  entityWorkflowId: string,
  jobIds: string[],
): Promise<WorkflowHandle> {
  let querying = QUERIES;

  const queryStorm = Promise.all(
    Array.from({ length: QUERIES ? QUERIERS : 0 }, async () => {
      // A query against a not-yet-started workflow, or a timed-out one, is not interesting.
      while (querying) {
        await client.workflow
          .getHandle(workflowId)
          .query(providerQueueJobsQuery)
          .catch(() => undefined);
      }
    }),
  );

  const handles = await Promise.all(
    jobIds.map((jobId) =>
      client.workflow.signalWithStart(providerQueueWorkflow, {
        workflowId,
        taskQueue: TASK_QUEUE,
        args: [{ maxConcurrentJobs: MAX_CONCURRENT, runningJobs: [] }],
        signal: publishToProviderQueueSignal,
        signalArgs: [{ jobId, entityWorkflowId, maxConcurrentJobs: MAX_CONCURRENT }],
      }),
    ),
  );

  querying = false;
  await queryStorm;
  return handles[0];
}

/**
 * Complete every job so the workflow's own idle-empty condition ends it.
 *
 * job_completed for a job that is still queued is a no-op (the id is not in runningJobs yet), so
 * this loops: complete whatever is currently running, let the dispatcher pull more off the queue,
 * repeat until both the queue and runningJobs are empty.
 */
async function drain(handle: WorkflowHandle): Promise<void> {
  for (let i = 0; i < 200; i++) {
    const state = (await handle.query(providerQueueJobsQuery).catch(() => undefined)) as
      { publishQueueCount: number; runningJobs: string[] } | undefined;
    if (!state) return;
    if (state.publishQueueCount === 0 && state.runningJobs.length === 0) return;
    for (const jobId of state.runningJobs) {
      await handle.signal(jobCompletedSignal, { jobId }).catch(() => undefined);
    }
    await sleep(150);
  }
}

/** Never let one wedged trial hang the whole run. */
async function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | undefined> {
  let timer: NodeJS.Timeout;
  const timeout = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), ms);
  });
  return Promise.race([p, timeout]).finally(() => clearTimeout(timer));
}

async function runTrial(client: Client, entityWorkflowId: string, workflowId: string): Promise<Trial> {
  const jobIds = Array.from({ length: JOBS }, (_, j) => `job-${j}`);

  const handle = await burstEnqueuesWhileQuerying(client, workflowId, entityWorkflowId, jobIds);
  await withTimeout(drain(handle), 60_000);
  // A wedged trial still yields a usable (partial) history to replay.
  if (
    (await withTimeout(
      handle.result().catch(() => undefined),
      30_000,
    )) === undefined
  ) {
    await handle.terminate('trial timed out').catch(() => undefined);
  }

  return { workflowId, history: await handle.fetchHistory() };
}

/**
 * One replay worker for all histories. Calling `Worker.runReplayHistory` in a loop re-constructs
 * the replay worker each time and the native runtime handle goes stale after the first one, which
 * surfaces as a confusing Rust downcast error rather than a replay failure.
 */
async function replayAllAgainstSameCode(trials: Trial[]): Promise<Trial[]> {
  const failures: Trial[] = [];

  for await (const result of Worker.runReplayHistories(
    { workflowsPath: require.resolve('./workflows'), replayName: 'nde-query-command-ordering' },
    trials,
  )) {
    if (result.error) {
      console.log(`  ${result.workflowId}: FAILED -- ${result.error.message}`);
      failures.push(trials.find((t) => t.workflowId === result.workflowId)!);
    }
  }
  return failures;
}

async function run() {
  const connection = await Connection.connect({ address: ADDRESS });
  const client = new Client({ connection, namespace: NAMESPACE });

  const runId = Date.now().toString(36);
  const entityWorkflowId = `entity-${runId}`;
  const trials: Trial[] = [];

  console.log(
    `queries=${QUERIES ? 'ON' : 'off'} jobs=${JOBS} queriers=${QUERIERS} ` +
      `attempts=${ATTEMPTS} maxConcurrentJobs=${MAX_CONCURRENT}\n`,
  );

  try {
    // Phase 1 -- the target for `execute_job`.
    await client.workflow.start(entityWorkflow, { workflowId: entityWorkflowId, taskQueue: TASK_QUEUE });

    // Phase 2 -- capture.
    for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
      trials.push(await runTrial(client, entityWorkflowId, `provider-queue-${runId}-${attempt}`));
      process.stdout.write(`\rcaptured ${attempt}/${ATTEMPTS}`);
    }
  } finally {
    await client.workflow
      .getHandle(entityWorkflowId)
      .terminate('done')
      .catch(() => undefined);
    await connection.close();
  }

  // Phase 3 -- replay.
  console.log(`\n\nreplaying ${trials.length} histories against the same code...\n`);
  const failures = await replayAllAgainstSameCode(trials);

  if (failures.length === 0) {
    console.log(`  all ${trials.length} replayed clean.\n`);
    console.log('No divergence. Grep the worker log for a Workflow Task delivered as TWO activations:');
    console.log("  grep -A1 'activate replaying=false' <worker.log>   # look for a chunk ending in S");
    return;
  }

  mkdirSync(HISTORY_DIR, { recursive: true });
  writeFileSync(OUT_FILE, historyToJSON(failures[0].history));

  console.log(`\n=== REPRODUCED: ${failures.length}/${trials.length} histories will not replay ===`);
  console.log(`history saved: ${OUT_FILE}`);
  console.log(`\nsee the diverging command order with:\n  pnpm replay ${OUT_FILE}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
