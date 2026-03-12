import { Client } from '@temporalio/client';
import { connectClient } from './connection';
import { setValueUpdate } from './workflows';

const workflowId = process.argv[2];
if (!workflowId) {
  console.error('Usage: ts-node src/send-updates.ts <workflow-id>');
  process.exit(1);
}

async function run() {
  const { connection, namespace } = await connectClient();
  const client = new Client({ connection, namespace });
  const handle = client.workflow.getHandle(workflowId);

  console.log(`Sending 3 updates to workflow ${workflowId}...`);

  for (const [i, value] of ['alpha', 'beta', 'gamma', 'delta'].entries()) {
    if (i > 0) await new Promise((resolve) => setTimeout(resolve, 4000));
    console.log(`Sending update ${i + 1} (${value})...`);
    handle
      .executeUpdate(setValueUpdate, { args: [value] })
      .then((result) => console.log(`Update ${i + 1} (${value}) completed:`, result))
      .catch((err) => console.error(`Update ${i + 1} (${value}) failed:`, err));
  }

  console.log('All updates dispatched.');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
