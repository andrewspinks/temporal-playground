import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { waitForSignals, turnSignal, flushUpdate } from './workflows';
import { nanoid } from 'nanoid';

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  // const handle = await client.workflow.start(waitForSignals, {
  //   taskQueue: 'wait-for-signals',
  //   workflowId: 'workflow-' + nanoid(),
  // });

  const handle = await client.workflow.signalWithStart(waitForSignals, {
    taskQueue: 'wait-for-signals',
    workflowId: 'workflow-' + nanoid(),
    signal: turnSignal,
    signalArgs: [`start-${Date.now()}`],
  });
  console.log(`Started workflow ${handle.workflowId}`);

  // await new Promise((r) => setTimeout(r, 50));

  // const item = `item-${Date.now()}`;
  // await handle.signal(turnSignal, item);

  // await new Promise((r) => setTimeout(r, 50));
  console.log('Sending update...');
  await handle.executeUpdate(flushUpdate);

  // console.log(await handle.result()); // Hello, Temporal!
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
