import { NativeConnection, Worker } from '@temporalio/worker';
import * as activities from './activities';
import { ADDRESS, NAMESPACE, TASK_QUEUE, tracing } from './shared';

// CACHE=0 disables the sticky cache, so every Workflow Task becomes a cold rebuild from history --
// the state 3 of 3 corrupted production Workflow Tasks were in. Note 1 is not a legal value; the
// SDK warns and rounds it up to 2. Use 0 or >= 2.
const CACHE = process.env.CACHE;

// Run several of these (WORKER_ID=1,2,3) to model the customer's multi-pod fleet.
const WORKER_ID = process.env.WORKER_ID ?? String(process.pid);

async function run() {
  const connection = await NativeConnection.connect({ address: ADDRESS });
  try {
    const worker = await Worker.create({
      connection,
      namespace: NAMESPACE,
      taskQueue: TASK_QUEUE,
      workflowsPath: require.resolve('./workflows'),
      activities,
      ...tracing(`w${WORKER_ID}`), // TEST INSTRUMENTATION
      ...(CACHE !== undefined ? { maxCachedWorkflows: Number(CACHE) } : {}),
    });
    console.log(`worker ${WORKER_ID} up  taskQueue=${TASK_QUEUE}  maxCachedWorkflows=${CACHE ?? 'default'}`);
    await worker.run();
  } finally {
    await connection.close();
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
