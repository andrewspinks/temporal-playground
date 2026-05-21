import { nanoid } from 'nanoid';
import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { syncCallerWorkflow, asyncCallerWorkflow, callNexusSignal, finishSignal } from './caller/workflows';

async function run() {
  const namespace = 'ts-nexus-caller-ns';
  const taskQueue = 'ts-nexus-caller-tq';

  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection, namespace });

  // const syncMsg = await client.workflow.execute(syncCallerWorkflow, {
  //   taskQueue,
  //   args: ['World'],
  //   workflowId: 'sync-' + nanoid(),
  // });
  // console.log(`Sync: ${syncMsg}`);

  // Start the long-running async caller workflow
  const workflowId = 'async-' + nanoid();
  const handle = await client.workflow.start(asyncCallerWorkflow, {
    taskQueue,
    args: [],
    workflowId,
  });
  console.log(`Started workflow: ${workflowId}`);

  // Signal it to call the nexus endpoint
  await handle.signal(callNexusSignal, 'World');
  console.log('Sent callNexus signal');

  // Finish the workflow and collect results
  // await handle.signal(finishSignal);
  // const results = await handle.result();
  // console.log(`Results: ${results}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
