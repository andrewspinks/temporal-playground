import { TestWorkflowEnvironment } from '@temporalio/testing';
import { after, before, describe, it } from 'mocha';
import { Worker } from '@temporalio/worker';
import { ApplicationFailure } from '@temporalio/workflow';
import { processTransfersWithChildren } from '../workflows-child';
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

describe('processTransfersWithChildren (child workflow) with mocked activities', () => {
  let testEnv: TestWorkflowEnvironment;

  before(async () => {
    testEnv = await TestWorkflowEnvironment.createTimeSkipping();
  });

  after(async () => {
    await testEnv?.teardown();
  });

  it('all receivers succeed on first attempt', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-success';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
      activities: {
        processPayment: async () => ({ transactionId: 'txn-mock' }),
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1', 'r2'])],
        workflowId: 'test-child-all-success',
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
    const taskQueue = 'test-child-non-retryable';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
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
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-child-non-retryable',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 1);
    assert.ok(smsSent[0].includes('Action required'));
  });

  it('user error: retries daily and succeeds on day 3', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-success';
    let attempt = 0;
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
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
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-child-retry-success',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'success');
    assert.equal(results[0].attempts, 4);
    assert.ok(smsSent.length >= 3);
  });

  it('user error: exhausts 14 retries and sends final failure SMS', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-exhausted';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
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
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-child-exhausted',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'failed');
    assert.equal(results[0].attempts, 15);
    const finalSms = smsSent[smsSent.length - 1];
    assert.ok(finalSms.includes('could not be processed'));
  });

  it('mixed results: one success, one flagged, one failed (parallel — find by receiverId)', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-mixed';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
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
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1', 'r2', 'r3'])],
        workflowId: 'test-child-mixed',
        taskQueue,
      }),
    );

    // Results arrive in parallel — use find() rather than positional indexing
    assert.equal(findResult(results, 'r1').status, 'success');
    assert.equal(findResult(results, 'r2').status, 'flagged');
    assert.equal(findResult(results, 'r3').status, 'failed');
  });

  it('user error escalates to non-retryable during retry window', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-escalation';
    let attempt = 0;

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child'),
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
      client.workflow.execute(processTransfersWithChildren, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-child-escalation',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 2);
  });
});
