import { nanoid } from 'nanoid';
import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { syncCallerWorkflow, asyncCallerWorkflow } from './caller/workflows';

async function run() {
  const namespace = 'ts-nexus-caller-ns';
  const taskQueue = 'ts-nexus-caller-tq';

  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection, namespace });

  const syncMsg = await client.workflow.execute(syncCallerWorkflow, {
    taskQueue,
    args: ['World'],
    workflowId: 'sync-' + nanoid(),
  });
  console.log(`Sync: ${syncMsg}`);

  const asyncMsg = await client.workflow.execute(asyncCallerWorkflow, {
    taskQueue,
    args: ['World'],
    workflowId: 'async-' + nanoid(),
  });
  console.log(`Async: ${asyncMsg}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
