/**
 * Starts the two workflows and nothing else, with fixed workflow IDs, so you can drive signals and
 * the query by hand from the CLI and watch the worker's command trace react.
 *
 * Use this to understand the mechanics; use `client.ts` to run the automated experiment.
 */
import { Client, Connection, WorkflowExecutionAlreadyStartedError } from '@temporalio/client';
import { ADDRESS, NAMESPACE, TASK_QUEUE } from './shared';
import { connectionWorkflow, providerQueueWorkflow } from './workflows';

const PROVIDER_QUEUE_WORKFLOW_ID = process.env.PROVIDER_QUEUE_ID ?? 'provider-queue-demo';
const CONNECTION_WORKFLOW_ID = process.env.CONNECTION_ID ?? 'connection-demo';

/** See TestKnobs.handlerHops. 2 puts the external signal mid-batch; 1 puts it last. */
const HANDLER_HOPS = Number(process.env.HANDLER_HOPS ?? 0);

/** Starting an already-running workflow is fine here -- just report it and carry on. */
async function startIfNotRunning(start: () => Promise<unknown>, workflowId: string): Promise<void> {
  try {
    await start();
    console.log(`  started  ${workflowId}`);
  } catch (err) {
    if (err instanceof WorkflowExecutionAlreadyStartedError) {
      console.log(`  already running  ${workflowId}`);
      return;
    }
    throw err;
  }
}

async function run() {
  const connection = await Connection.connect({ address: ADDRESS });
  const client = new Client({ connection, namespace: NAMESPACE });

  try {
    await startIfNotRunning(
      () => client.workflow.start(connectionWorkflow, { workflowId: CONNECTION_WORKFLOW_ID, taskQueue: TASK_QUEUE }),
      CONNECTION_WORKFLOW_ID,
    );

    await startIfNotRunning(
      () =>
        client.workflow.start(providerQueueWorkflow, {
          workflowId: PROVIDER_QUEUE_WORKFLOW_ID,
          taskQueue: TASK_QUEUE,
          args: [CONNECTION_WORKFLOW_ID, { handlerHops: HANDLER_HOPS }],
        }),
      PROVIDER_QUEUE_WORKFLOW_ID,
    );
  } finally {
    await connection.close();
  }

  // Pass the address explicitly so the CLI provably talks to the same server as the SDK.
  const pq = `--address ${ADDRESS} --namespace ${NAMESPACE} --workflow-id ${PROVIDER_QUEUE_WORKFLOW_ID}`;
  console.log(`
handlerHops=${HANDLER_HOPS}   (restart with HANDLER_HOPS=2 to move the external signal mid-batch)

Enqueue a job  ->  worker traces: commands=AS
  temporal workflow signal ${pq} --name publish_to_provider_queue --input '"job-1"'

Read the queue depth (this is the input that is NEVER written to history)
  temporal workflow query ${pq} --type provider_queue_jobs

Finish the workflow
  temporal workflow signal ${pq} --name stop

Show what actually got recorded
  temporal workflow show ${pq}

To see SEVERAL signals land in ONE Workflow Task -- the precondition for the bug -- nothing must be
polling while you send them. Easiest reliable order, from a clean slate:
  1. stop the worker
  2. run this starter (it does not need a worker to start workflows)
  3. send publish_to_provider_queue a few times
  4. start the worker
The trace then shows one activation carrying every signal at once, e.g.
    activate replaying=false jobs=[initializeWorkflow, signalWorkflow x5]
      commands=AAAAAS
Re-run steps 1-4 with HANDLER_HOPS=2 and fresh IDs and the same batch comes out as ASAAAA instead --
one extra microtask hop moves the external signal across the batch. That mid-batch position is what
production recorded and then could not replay.

Prefer this over "stop the worker mid-run": that path waits out the ~10s sticky-queue timeout first,
which is what production hit (a WorkflowTaskTimedOut with no matching Started), but it is slower and
can stall on the dev server.
`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
