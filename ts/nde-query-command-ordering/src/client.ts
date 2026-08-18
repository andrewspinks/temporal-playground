/**
 * The starter. Runs the experiment in three phases:
 *
 *   1. start one connectionWorkflow -- the target for `execute_job`
 *   2. run ATTEMPTS independent trials; each starts a fresh providerQueueWorkflow, hammers it, and
 *      captures its complete history
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
  connectionWorkflow,
  providerQueueJobsQuery,
  providerQueueWorkflow,
  publishToProviderQueueSignal,
  stopSignal,
} from './workflows';

type History = Parameters<typeof historyToJSON>[0];
type Trial = { workflowId: string; history: History };

/** QUERIES=off is the control arm: identical run with the unrecorded input removed. */
const QUERIES = process.env.QUERIES !== 'off';
/** Signals per burst. Needs to be big enough that several land in one Workflow Task. */
const JOBS = Number(process.env.JOBS ?? 12);
/** Independent trials. */
const ATTEMPTS = Number(process.env.ATTEMPTS ?? 25);
/** Concurrent queriers, modelling the customer's many parallel producers. */
const QUERIERS = Number(process.env.QUERIERS ?? 6);
/** See TestKnobs.handlerHops in workflows.ts -- the experimental lever. */
const HANDLER_HOPS = Number(process.env.HANDLER_HOPS ?? 0);

const HISTORY_DIR = path.resolve(__dirname, '../../../histories');
const OUT_FILE = path.join(HISTORY_DIR, 'nde-query-ordering-1.16.1.json');

/**
 * The production traffic pattern: a query immediately before every enqueue, from many producers at
 * once.
 *
 * Modelled as a query storm running alongside a tight signal burst rather than
 * `await query(); await signal()` per job -- serialising it that way spaces the signals out, and we
 * would never get several into one Workflow Task, which is the precondition for the bug.
 */
async function burstSignalsWhileQuerying(handle: WorkflowHandle): Promise<void> {
  let querying = QUERIES;

  const queryStorm = Promise.all(
    Array.from({ length: QUERIES ? QUERIERS : 0 }, async () => {
      // A timed-out query only means the worker is saturated; not interesting.
      while (querying) await handle.query(providerQueueJobsQuery).catch(() => undefined);
    }),
  );

  await Promise.all(Array.from({ length: JOBS }, (_, j) => handle.signal(publishToProviderQueueSignal, `job-${j}`)));

  querying = false;
  await queryStorm;
}

/**
 * One trial = one fresh workflow. Fresh each time so the trials are independent and each history
 * stays short enough that replaying it is cheap.
 */
async function runTrial(client: Client, connectionWorkflowId: string, workflowId: string): Promise<Trial> {
  const handle = await client.workflow.start(providerQueueWorkflow, {
    workflowId,
    taskQueue: TASK_QUEUE,
    args: [connectionWorkflowId, { handlerHops: HANDLER_HOPS }],
  });

  await burstSignalsWhileQuerying(handle);

  // Run it to completion so the captured history is complete.
  await handle.signal(stopSignal);
  await handle.result().catch(() => undefined);

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
  const connectionWorkflowId = `connection-${runId}`;
  const trials: Trial[] = [];

  console.log(
    `queries=${QUERIES ? 'ON' : 'off'} jobs=${JOBS} queriers=${QUERIERS} ` +
      `attempts=${ATTEMPTS} handlerHops=${HANDLER_HOPS}\n`,
  );

  try {
    // Phase 1 -- the target for `execute_job`.
    await client.workflow.start(connectionWorkflow, { workflowId: connectionWorkflowId, taskQueue: TASK_QUEUE });

    // Phase 2 -- capture.
    for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
      trials.push(await runTrial(client, connectionWorkflowId, `provider-queue-${runId}-${attempt}`));
      process.stdout.write(`\rcaptured ${attempt}/${ATTEMPTS}`);
    }
  } finally {
    await client.workflow
      .getHandle(connectionWorkflowId)
      .terminate('done')
      .catch(() => undefined);
    await connection.close();
  }

  // Phase 3 -- replay.
  console.log(`\n\nreplaying ${trials.length} histories against the same code...\n`);
  const failures = await replayAllAgainstSameCode(trials);

  if (failures.length === 0) {
    console.log(`  all ${trials.length} replayed clean.\n`);
    console.log('No divergence. Compare the [w*] command strings in the worker log, then try:');
    console.log('  HANDLER_HOPS=2 pnpm workflow     (puts S mid-batch, where a 1-hop shift matters)');
    console.log('  JOBS=30 ATTEMPTS=50 pnpm workflow');
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
