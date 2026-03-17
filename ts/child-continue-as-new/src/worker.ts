import { NativeConnection, Worker } from '@temporalio/worker';
import * as activities from './activities';

async function run() {
  const connection = await NativeConnection.connect({ address: 'localhost:7234' });
  const worker = await Worker.create({
    connection,
    workflowsPath: require.resolve('./workflows'),
    activities,
    taskQueue: 'child-workflows',
  });
  await worker.run();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
