/**
 * Approach 4: Self-chaining via startDelay
 *
 * Starts the first billing workflow. After each run, an activity starts the *next*
 * workflow execution with `startDelay` set to the duration until the next last-day-of-month.
 * Each billing cycle is a completely independent workflow execution.
 *
 * Trade-offs:
 *   + 4 actions/cycle — startDelay is free (no TIMER_STARTED event)
 *   + Precise last-day-of-month (computed at runtime)
 *   + Clean per-cycle history (each execution is independent)
 *   - Not in Schedules UI
 *   - Chain breaks if the workflow is terminated or the chain activity hits a non-retryable error;
 *     transient failures are retried automatically, but unlike a Schedule there is no persistent
 *     server-side entity to restart the chain if the running workflow is killed first
 *   - Each workflow has a unique ID — harder to find without search attributes
 *
 * Actions/cycle: 4  (1 WF start + 2 activities + 1 chain activity; startDelay is free)
 */
import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { billingChainWorkflow } from './workflows';
import { nextBillingDate } from './billing-helpers';

const CUSTOMER_ID = 'cust-001';

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  // First execution runs immediately. It will chain the next one with a startDelay.
  const now = new Date();
  const workflowId = `billing-chain-${CUSTOMER_ID}-${now.toISOString().slice(0, 10)}`;
  const next = nextBillingDate(now, 9);

  const handle = await client.workflow.start(billingChainWorkflow, {
    taskQueue: 'schedules',
    workflowId,
    args: [CUSTOMER_ID],
  });

  console.log(`Started workflow '${handle.workflowId}'.`);
  console.log('Bills immediately. The workflow will chain the next execution with startDelay.');
  console.log(`Next scheduled billing: ${next.toISOString()} (last day of next month)`);
  console.log('\nUseful commands:');
  console.log(`  temporal workflow describe --workflow-id ${workflowId}`);
  console.log(`  temporal workflow list     --query 'WorkflowId like "billing-chain-${CUSTOMER_ID}%"'`);

  await connection.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
