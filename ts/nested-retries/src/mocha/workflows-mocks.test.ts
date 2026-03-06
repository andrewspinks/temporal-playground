import { TestWorkflowEnvironment } from '@temporalio/testing';
import { after, before, describe, it } from 'mocha';
import { Worker } from '@temporalio/worker';
import { ApplicationFailure } from '@temporalio/workflow';
import { processTransfers } from '../workflows';
import type { TransferRequest, TransferResult } from '../types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR } from '../types';
import assert from 'assert';

function makeRequest(receiverIds: string[] = ['r1']): TransferRequest {
  return {
    account: { accountId: 'account-1', phoneNumber: '+15551234567' },
    receivers: receiverIds.map((id) => ({ receiverId: id, receiverName: `Receiver ${id}`, amount: 1000 })),
  };
}

describe('processTransfers workflow with mocked activities', () => {
  let testEnv: TestWorkflowEnvironment;

  before(async () => {
    testEnv = await TestWorkflowEnvironment.createTimeSkipping();
  });

  after(async () => {
    await testEnv?.teardown();
  });

  it('all receivers succeed on first attempt', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-success';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities: {
        processPayment: async () => ({ transactionId: 'txn-mock' }),
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1', 'r2'])],
        workflowId: 'test-mock-all-success',
        taskQueue,
      }),
    );

    assert.equal(results.length, 2);
    results.forEach((r: TransferResult) => {
      assert.equal(r.status, 'success');
      assert.equal(r.attempts, 1);
    });
  });

  it('non-retryable error: flags account and sends SMS', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-non-retryable';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
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
        workflowId: 'test-mock-non-retryable',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 1);
    assert.ok(smsSent[0].includes('Action required'));
  });

  it('user error: retries daily and succeeds on day 3', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-retry-success';
    let attempt = 0;
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities: {
        processPayment: async () => {
          attempt++;
          if (attempt <= 3) {
            throw ApplicationFailure.create({
              message: 'Insufficient funds',
              type: USER_PAYMENT_ERROR,
              nonRetryable: true,
            });
          }
          return { transactionId: 'txn-retry-success' };
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
        flagForManualReview: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-mock-retry-success',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'success');
    assert.equal(results[0].attempts, 4); // 1 initial + 3 daily retries
    assert.ok(smsSent.length >= 3); // initial failure + 2 "failed again" + success breaks loop
  });

  it('user error: exhausts 14 retries and sends final failure SMS', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-exhausted';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities: {
        processPayment: async () => {
          throw ApplicationFailure.create({
            message: 'Insufficient funds',
            type: USER_PAYMENT_ERROR,
            nonRetryable: true,
          });
        },
        sendSmsNotification: async (_phone: string, msg: string) => { smsSent.push(msg); },
        flagForManualReview: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-mock-exhausted',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'failed');
    assert.equal(results[0].attempts, 15); // 1 initial + 14 daily retries
    const finalSms = smsSent[smsSent.length - 1];
    assert.ok(finalSms.includes('could not be processed'));
  });

  it('mixed results: one success, one flagged, one failed', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-mixed';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities: {
        processPayment: async (_accountId: string, receiverId: string) => {
          if (receiverId === 'r1') return { transactionId: 'txn-r1' };
          if (receiverId === 'r2') {
            throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
          }
          throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: true });
        },
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1', 'r2', 'r3'])],
        workflowId: 'test-mock-mixed',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'success');  // r1
    assert.equal(results[1].status, 'flagged');  // r2 - expired card
    assert.equal(results[2].status, 'failed');   // r3 - insufficient funds exhausted
  });

  it('user error escalates to non-retryable during retry window', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-mock-escalation';
    let attempt = 0;

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities: {
        processPayment: async () => {
          attempt++;
          if (attempt === 1) {
            throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: true });
          }
          throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
        },
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-mock-escalation',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 2); // initial + 1 retry before escalation
  });
});
