// @@@SNIPSTART typescript-hello-client
import { Client } from '@temporalio/client';
import { connectClient } from './connection';
import { example } from './workflows';
import { nanoid } from 'nanoid';

async function run() {
  const { connection, namespace } = await connectClient();
  const client = new Client({ connection, namespace });

  const handle = await client.workflow.start(example, {
    taskQueue: 'hello-world',
    // type inference works! args: [name: string]
    args: ['Temporal'],
    // in practice, use a meaningful business ID, like customerId or transactionId
    workflowId: 'workflow-' + nanoid(),
  });
  console.log(`Started workflow ${handle.workflowId}`);

  // optional: wait for client result
  console.log(await handle.result()); // Hello, Temporal!
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
// @@@SNIPEND
