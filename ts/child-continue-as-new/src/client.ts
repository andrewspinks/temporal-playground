import { Client, Connection } from '@temporalio/client';
import { parentWorkflow } from './workflows';

async function run() {
  const connection = await Connection.connect({ address: 'localhost:7234' });
  const client = new Client({ connection });

  const handle = await client.workflow.start(parentWorkflow, {
    taskQueue: 'child-workflows',
    workflowId: 'parent-repro-0',
  });
  console.log(`Started workflow ${handle.workflowId}, run ID: ${handle.firstExecutionRunId}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
