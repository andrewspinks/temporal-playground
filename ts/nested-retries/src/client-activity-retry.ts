import { Connection, Client } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { processTransfers } from './workflows-activity-retry';
import type { TransferRequest } from './types';
import { nanoid } from 'nanoid';

const RECEIVERS = [
  { receiverId: 'acme',    receiverName: 'Acme Corp',   amount: 5000 },
  { receiverId: 'globex',  receiverName: 'Globex Ltd',  amount: 2500 },
  { receiverId: 'initech', receiverName: 'Initech Inc', amount: 1000 },
] as const;

const SCENARIOS: Array<{ name: string; description: string; request: TransferRequest }> = [
  {
    name: 'all-success',
    description: 'Happy path — all 3 receivers charged successfully on first attempt',
    request: {
      account: { accountId: 'account-happy', phoneNumber: '+15550000001' },
      receivers: [{ ...RECEIVERS[0] }, { ...RECEIVERS[1] }, { ...RECEIVERS[2] }],
    },
  },
  {
    name: 'intermittent-self-heals',
    description: 'Intermittent network errors — Temporal retries silently, succeeds on attempt 3',
    request: {
      account: { accountId: 'account-flaky', phoneNumber: '+15550000002' },
      receivers: [
        { ...RECEIVERS[0], simulateError: 'intermittent', succeedAfterAttempts: 2 },
        { ...RECEIVERS[1], simulateError: 'intermittent', succeedAfterAttempts: 2 },
        { ...RECEIVERS[2] },
      ],
    },
  },
  {
    name: 'non-retryable-card-expired',
    description: 'Permanent card failure — flagged for manual review, no retries',
    request: {
      account: { accountId: 'account-expired', phoneNumber: '+15550000003' },
      receivers: [
        { ...RECEIVERS[0], simulateError: 'non-retryable' },
        { ...RECEIVERS[1], simulateError: 'non-retryable' },
        { ...RECEIVERS[2], simulateError: 'non-retryable' },
      ],
    },
  },
  {
    name: 'insufficient-funds-recovers',
    description: 'Insufficient funds — activity retried daily by Temporal, account topped up on day 3',
    request: {
      account: { accountId: 'account-broke-then-rich', phoneNumber: '+15550000004' },
      receivers: [
        { ...RECEIVERS[0], simulateError: 'user-error', succeedAfterAttempts: 3 },
        { ...RECEIVERS[1] },
        { ...RECEIVERS[2] },
      ],
    },
  },
  {
    name: 'insufficient-funds-exhausted',
    description: 'Insufficient funds — activity retried for 14 days, never recovers, final failure SMS',
    request: {
      account: { accountId: 'account-always-broke', phoneNumber: '+15550000005' },
      receivers: [
        { ...RECEIVERS[0], simulateError: 'user-error' },
        { ...RECEIVERS[1] },
        { ...RECEIVERS[2] },
      ],
    },
  },
  {
    name: 'mixed-all-paths',
    description: 'One of each: success, expired card (flagged), insufficient funds (recovers on day 2)',
    request: {
      account: { accountId: 'account-mixed', phoneNumber: '+15550000006' },
      receivers: [
        { ...RECEIVERS[0] },
        { ...RECEIVERS[1], simulateError: 'non-retryable' },
        { ...RECEIVERS[2], simulateError: 'user-error', succeedAfterAttempts: 2 },
      ],
    },
  },
];

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  const runId = nanoid(6);
  console.log(`Run ID: ${runId}\n`);

  for (const scenario of SCENARIOS) {
    const workflowId = `transfer-activity-retry-${runId}-${scenario.name}`;
    await client.workflow.start(processTransfers, {
      taskQueue: 'payment-transfers-activity-retry',
      args: [scenario.request],
      workflowId,
    });
    console.log(`✓ ${workflowId}`);
    console.log(`  ${scenario.description}\n`);
  }

  console.log(`Started ${SCENARIOS.length} workflows. Daily retries are invisible in history — check the Temporal UI activity retry count.`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
