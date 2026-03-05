/**
 * Approach 3: continueAsNew + sleep
 *
 * Starts a single long-lived workflow: bill → sleep until last-day-of-next-month →
 * continueAsNew. No Schedule entity at all. Cheapest approach — fewest actions per cycle.
 *
 * Trade-offs:
 *   + Cheapest: 4 actions/cycle (1 continueAsNew + 2 activities + 1 timer)
 *   + Precise last-day-of-month (computed at runtime)
 *   + Self-contained: no schedule infrastructure
 *   - Not visible in Schedules UI
 *   - No native pause/backfill — must cancel and restart
 *   - Each continueAsNew is a new run under the same workflow ID
 *
 * Actions/cycle: 4  (1 continueAsNew + 2 activities + 1 timer)
 */
import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { billingContinueAsNewWorkflow } from './workflows';

const CUSTOMER_ID = 'cust-001';
const WORKFLOW_ID = `billing-loop-${CUSTOMER_ID}`;

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  const handle = await client.workflow.start(billingContinueAsNewWorkflow, {
    taskQueue: 'schedules',
    workflowId: WORKFLOW_ID,
    args: [CUSTOMER_ID],
  });

  console.log(`Started workflow '${handle.workflowId}'.`);
  console.log('Bills immediately, then sleeps until the last day of next month and repeats via continueAsNew.');
  console.log('\nUseful commands:');
  console.log(`  temporal workflow describe --workflow-id ${WORKFLOW_ID}`);
  console.log(`  temporal workflow list`);
  console.log(`  temporal workflow cancel   --workflow-id ${WORKFLOW_ID}   # stop the loop`);

  await connection.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
