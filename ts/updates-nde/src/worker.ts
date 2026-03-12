// @@@SNIPSTART typescript-hello-worker
import * as fs from 'fs';
import { Worker, Runtime, DefaultLogger, LogEntry } from '@temporalio/worker';

import * as activities from './activities';
import { connectWorker } from './connection';

const logFile = fs.createWriteStream('worker.log', { flags: 'a' });

function writeToFile(entry: LogEntry): void {
  const { level, timestampNanos, message, meta } = entry;
  const ts = new Date(Number(timestampNanos / 1_000_000n)).toISOString();
  const line = JSON.stringify({ ts, level, message, ...meta }) + '\n';
  logFile.write(line);
}

async function run() {
  Runtime.install({
    logger: new DefaultLogger('DEBUG', writeToFile),
    telemetryOptions: {
      logging: {
        filter: { core: 'DEBUG', other: 'WARN' },
        forward: {},
      },
    },
  });
  // Step 1: Establish a connection with Temporal server.
  //
  // Reads TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TEMPORAL_API_KEY, etc. from
  // the environment (or TEMPORAL_CONFIG_FILE). Works for both local dev and
  // Temporal Cloud — see src/connection.ts for details.
  const { connection, namespace } = await connectWorker();
  try {
    // Step 2: Register Workflows and Activities with the Worker.
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue: 'hello-world',
      // Workflows are registered using a path as they run in a separate JS context.
      workflowsPath: require.resolve('./workflows'),
      activities,
    });

    // Step 3: Start accepting tasks on the `hello-world` queue
    //
    // The worker runs until it encounters an unexpected error or the process receives a shutdown signal registered on
    // the SDK Runtime object.
    //
    // By default, worker logs are written via the Runtime logger to STDERR at INFO level.
    //
    // See https://typescript.temporal.io/api/classes/worker.Runtime#install to customize these defaults.
    await worker.run();
  } finally {
    // Close the connection once the worker has stopped
    await connection.close();
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
// @@@SNIPEND
