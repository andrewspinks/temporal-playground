/**
 * Starts the two workflows and nothing else, with fixed workflow IDs, so you can drive signals and
 * the query by hand from the CLI and watch the worker's command trace react.
 *
 * Use this to understand the mechanics; use `client.ts` to run the automated experiment.
 */
import { Client, Connection, WorkflowExecutionAlreadyStartedError } from '@temporalio/client';
import { ADDRESS, NAMESPACE, TASK_QUEUE } from './shared';
import { entityWorkflow, providerQueueWorkflow } from './workflows';

const PROVIDER_QUEUE_WORKFLOW_ID = process.env.PROVIDER_QUEUE_ID ?? 'provider-queue-demo';
const ENTITY_WORKFLOW_ID = process.env.ENTITY_ID ?? 'entity-demo';
const MAX_CONCURRENT = Number(process.env.MAX_CONCURRENT ?? 10);

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
      () => client.workflow.start(entityWorkflow, { workflowId: ENTITY_WORKFLOW_ID, taskQueue: TASK_QUEUE }),
      ENTITY_WORKFLOW_ID,
    );

    await startIfNotRunning(
      () =>
        client.workflow.start(providerQueueWorkflow, {
          workflowId: PROVIDER_QUEUE_WORKFLOW_ID,
          taskQueue: TASK_QUEUE,
          args: [{ maxConcurrentJobs: MAX_CONCURRENT, runningJobs: [] }],
        }),
      PROVIDER_QUEUE_WORKFLOW_ID,
    );
  } finally {
    await connection.close();
  }

  // Pass the address explicitly so the CLI provably talks to the same server as the SDK.
  const pq = `--address ${ADDRESS} --namespace ${NAMESPACE} --workflow-id ${PROVIDER_QUEUE_WORKFLOW_ID}`;
  const job = (id: string) =>
    `'{"jobId":"${id}","entityWorkflowId":"${ENTITY_WORKFLOW_ID}","maxConcurrentJobs":${MAX_CONCURRENT}}'`;

  console.log(`
Enqueue a job  ->  worker traces one activation, commands=AS
  temporal workflow signal ${pq} --name publish_to_provider_queue --input ${job('job-1')}

Read the queue depth (the input that is NEVER written to history)
  temporal workflow query ${pq} --type provider_queue_jobs

Complete a job (frees a slot; also schedules a metrics activity)
  temporal workflow signal ${pq} --name job_completed --input '{"jobId":"job-1"}'

Show what actually got recorded
  temporal workflow show ${pq}

To get SEVERAL signals into ONE Workflow Task -- the precondition for the bug -- nothing must be
polling while you send them. From a clean slate:
  1. stop the worker
  2. run this starter (it does not need a worker to start workflows)
  3. send publish_to_provider_queue a few times
  4. start the worker

WHAT TO LOOK FOR. Within a single activation the metrics activities are always pushed before the
external signal, so a batch traces as one activation ending in S:

    activate replaying=false jobs=[initializeWorkflow, signalWorkflow x5]
      commands=AAAAAS

The corrupted production tasks instead recorded S *mid* batch (AAAASAA / AASAAAAAA / ASA). That is
only possible if one Workflow Task was delivered as TWO activations, e.g.

    activate replaying=false jobs=[signalWorkflow x4]
      commands=AAAAS
    activate replaying=false jobs=[signalWorkflow x2]
      commands=AA

Two activate lines for one Workflow Task is the thing to hunt for. Replay delivers one.
`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
