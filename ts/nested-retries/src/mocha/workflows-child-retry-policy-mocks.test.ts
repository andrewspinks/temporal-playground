import { TestWorkflowEnvironment } from '@temporalio/testing';
import { after, before, describe, it } from 'mocha';
import { Worker } from '@temporalio/worker';
import { ApplicationFailure } from '@temporalio/workflow';
import { processTransfersWithRetryPolicy } from '../workflows-child-retry-policy';
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

describe('processTransfersWithRetryPolicy (child retry policy) with mocked activities', () => {
  let testEnv: TestWorkflowEnvironment;

  before(async () => {
    testEnv = await TestWorkflowEnvironment.createTimeSkipping();
  });

  after(async () => {
    await testEnv?.teardown();
  });

  it('all receivers succeed on first attempt', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-policy-success';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
      activities: {
        processPayment: async () => ({ transactionId: 'txn-mock' }),
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1', 'r2'])],
        workflowId: 'test-retry-policy-all-success',
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
    const taskQueue = 'test-child-retry-policy-non-retryable';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
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
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-retry-policy-non-retryable',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 1);
    assert.ok(smsSent[0].includes('Action required'));
  });

  it('user error: Temporal retries daily and succeeds on attempt 4', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-policy-retry-success';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
      activities: {
        // workflowAttempt (6th arg) increments per child retry run — no closure counter needed
        processPayment: async (_d: string, _c: string, _a: number, _se: unknown, _saa: unknown, workflowAttempt: number | undefined) => {
          if ((workflowAttempt ?? 1) <= 3) {
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
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-retry-policy-retry-success',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'success');
    assert.equal(results[0].attempts, 4);
    // 3 "retry tomorrow" SMSes (attempts 1–3)
    assert.ok(smsSent.length >= 3);
    assert.ok(smsSent.every((m) => m.includes("We'll retry tomorrow")));
  });

  it('user error: exhausts 14 retries, parent returns failed, child sends final SMS', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-policy-exhausted';
    const smsSent: string[] = [];

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
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
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-retry-policy-exhausted',
        taskQueue,
      }),
    );

    // Parent catches ChildWorkflowFailure and returns a synthetic failed result
    assert.equal(results[0].status, 'failed');
    assert.equal(results[0].attempts, 15);
    // Child sent final "could not be processed" SMS on its last attempt
    const finalSms = smsSent[smsSent.length - 1];
    assert.ok(finalSms.includes('could not be processed'));
  });

  it('mixed results: one success, one flagged, one user-error that recovers (parallel — find by receiverId)', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-policy-mixed';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
      activities: {
        processPayment: async (_d: string, receiverId: string, _a: number, _se: unknown, _saa: unknown, workflowAttempt: number | undefined) => {
          if (receiverId === 'r1') return { transactionId: 'txn-r1' };
          if (receiverId === 'r2') {
            throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
          }
          // r3: user error, succeeds on attempt 2
          if ((workflowAttempt ?? 1) <= 1) {
            throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: true });
          }
          return { transactionId: 'txn-r3' };
        },
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1', 'r2', 'r3'])],
        workflowId: 'test-retry-policy-mixed',
        taskQueue,
      }),
    );

    assert.equal(findResult(results, 'r1').status, 'success');
    assert.equal(findResult(results, 'r2').status, 'flagged');
    assert.equal(findResult(results, 'r3').status, 'success');
    assert.equal(findResult(results, 'r3').attempts, 2);
  });

  it('user error escalates to non-retryable on retry attempt', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-child-retry-policy-escalation';
    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows-child-retry-policy'),
      activities: {
        processPayment: async (_d: string, _c: string, _a: number, _se: unknown, _saa: unknown, workflowAttempt: number | undefined) => {
          const attempt = workflowAttempt ?? 1;
          if (attempt === 1) {
            throw ApplicationFailure.create({ message: 'Insufficient funds', type: USER_PAYMENT_ERROR, nonRetryable: true });
          }
          throw ApplicationFailure.create({ message: 'Card expired', type: NON_RETRYABLE_PAYMENT_ERROR, nonRetryable: true });
        },
        sendSmsNotification: async () => {},
      },
    });

    const results = await worker.runUntil(
      client.workflow.execute(processTransfersWithRetryPolicy, {
        args: [makeRequest(['r1'])],
        workflowId: 'test-retry-policy-escalation',
        taskQueue,
      }),
    );

    assert.equal(results[0].status, 'flagged');
    assert.equal(results[0].attempts, 2);
  });
});
