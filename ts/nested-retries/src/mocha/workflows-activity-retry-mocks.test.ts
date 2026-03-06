import { TestWorkflowEnvironment } from '@temporalio/testing';
import { after, before, describe, it } from 'mocha';
import { Worker } from '@temporalio/worker';
import { ApplicationFailure } from '@temporalio/workflow';
import { processTransfers } from '../workflows-activity-retry';
import type { TransferRequest, TransferResult } from '../types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR } from '../types';
import assert from 'assert';

function makeRequest(receiverIds: string[] = ['r1']): TransferRequest {
  return {
    account: { accountId: 'account-1', phoneNumber: '+15551234567' },
    receivers: receiverIds.map((id) => ({ receiverId: id, receiverName: `Receiver ${id}`, amount: 1000 })),
  };
}

function findResult(results: TransferResult[], receiverId: string): TransferResult {
  const r = results.find((r) => r.receiverId === receiverId);
  if (!r) throw new Error(`No result for receiverId=${receiverId}`);
  return r;
}

describe('processTransfers (activity retry policy) with mocked activities', () => {
  let testEnv: TestWorkflowEnvironment;

  before(async () => {
    testEnv = await TestWorkflowEnvironment.createTimeSkipping();
  });

  after(async () => {
    await testEnv?.teardown();
  });

  it('all receivers succeed on first attempt', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-success';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async () => ({ transactionId: 'txn-mock', attempt: 1 }),
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1', 'r2'])],
        workflowId: 'test-activity-retry-all-success',
        taskQueue,
      }),
    );

    assert.equal(results.length, 2);
    results.forEach((r: TransferResult) => {
      assert.equal(r.status, 'success');
      assert.equal(r.attempts, 1);
    });
  });

  it('non-retryable error: sends SMS', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-non-retryable';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async () => {
          throw ApplicationFailure.create({
            message: 'Card expired',
            type: NON_RETRYABLE_PAYMENT_ERROR,
            nonRetryable: true,
          });
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-activity-retry-non-retryable',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 1);
    assert.ok(smsSent[0].includes('Action required'));
  });

  it('user error: Temporal retries daily and succeeds on day 3', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-daily-success';
    // callCount covers all invocations across both proxies:
    //   call 1 = tryPaymentFast  (USER_PAYMENT_ERROR → workflow switches to tryPaymentDaily)
    //   call 2 = tryPaymentDaily attempt 1
    //   call 3 = tryPaymentDaily attempt 2
    //   call 4 = tryPaymentDaily attempt 3 → success, attempt: 3
    let callCount = 0;
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async () => {
          callCount++;
          if (callCount < 4) {
            // nonRetryable: false is required so tryPaymentDaily's retry policy fires
            throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: false });
          }
          return { transactionId: 'txn-daily-success', attempt: 3 };
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-activity-retry-daily-success',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'success');
    assert.equal(results[0].attempts, 4); // 1 fast + 3 daily
    assert.equal(smsSent.length, 2); // upfront "retrying daily" + final "processed successfully"
    assert.ok(smsSent[0].includes("retry daily"));
    assert.ok(smsSent[1].includes("processed successfully"));
  });

  it('user error: exhausts 14 daily retries', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-exhausted';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async () => {
          throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: false });
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-activity-retry-exhausted',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'failed');
    assert.equal(results[0].attempts, 15); // 1 fast + 14 daily
    assert.equal(smsSent.length, 2); // upfront "retrying daily" + final "could not be processed"
    assert.ok(smsSent[smsSent.length - 1].includes('could not be processed'));
  });

  it('mixed results: one success, one flagged, one failed (parallel — find by receiverId)', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-mixed';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async (_accountId: string, receiverId: string) => {
          if (receiverId === 'r1') return { transactionId: 'txn-r1', attempt: 1 };
          if (receiverId === 'r2') {
            throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
          }
          // r3: always user error — exhausts all retries
          throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: false });
        },
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1', 'r2', 'r3'])],
        workflowId: 'test-activity-retry-mixed',
        taskQueue,
      }),
    );

    assert.equal(findResult(results, 'r1').status, 'success');
    assert.equal(findResult(results, 'r2').status, 'flagged');
    assert.equal(findResult(results, 'r3').status, 'failed');
  });

  it('user error escalates to non-retryable during daily retry window', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-activity-retry-escalation';
    // call 1 = tryPaymentFast: USER_PAYMENT_ERROR → enters daily retry path
    // call 2 = tryPaymentDaily attempt 1: NON_RETRYABLE_PAYMENT_ERROR → fails immediately
    let callCount = 0;
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-activity-retry'),
      activities: {
        processPayment: async () => {
          callCount++;
          if (callCount === 1) {
            throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: false });
          }
          throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-activity-retry-escalation',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    // Upfront "retrying daily" SMS + final "Action required" SMS
    assert.equal(smsSent.length, 2);
    assert.ok(smsSent[smsSent.length - 1].includes('Action required'));
  });
});
