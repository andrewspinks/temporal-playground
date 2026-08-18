/**
 * Replays one saved history with the command tracer on, so you can read the replay pass's command
 * strings and compare them against the live pass in the worker log.
 */
import { readFileSync } from 'fs';
import { Worker } from '@temporalio/worker';
import { tracing } from './shared';

// `Worker.validateHistory` auto-detects proto3-JSON (string eventIds), so a raw JSON.parse is enough.
async function run() {
  const file = process.argv[2];
  if (!file) {
    console.error('usage: pnpm replay <history.json>');
    process.exit(1);
  }

  const history = JSON.parse(readFileSync(file, 'utf8'));
  try {
    await Worker.runReplayHistory(
      {
        workflowsPath: require.resolve('./workflows'),
        replayName: 'nde-query-command-ordering',
        ...tracing('replay'), // TEST INSTRUMENTATION
      },
      history,
    );
    console.log('\nreplayed clean');
  } catch (err) {
    console.log(`\n=== REPLAY FAILED ===\n${(err as Error).message}`);
    process.exitCode = 1;
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
