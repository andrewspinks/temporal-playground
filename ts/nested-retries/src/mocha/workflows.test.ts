import { TestWorkflowEnvironment } from '@temporalio/testing';
import { before, after, describe, it } from 'mocha';
import { Worker } from '@temporalio/worker';
import { processTransfers } from '../workflows';
import * as activities from '../activities';
import type { TransferRequest } from '../types';
import assert from 'assert';

describe('processTransfers workflow (integration)', () => {
  let testEnv: TestWorkflowEnvironment;

  before(async () => {
    testEnv = await TestWorkflowEnvironment.createLocal();
  });

  after(async () => {
    await testEnv?.teardown();
  });

  it('processes all receivers successfully with real activities', async () => {
    const { client, nativeConnection } = testEnv;
    const taskQueue = 'test-integration';

    const worker = await Worker.create({
      connection: nativeConnection,
      taskQueue,
      workflowsPath: require.resolve('../workflows'),
      activities,
    });

    const request: TransferRequest = {
      account: { accountId: 'account-1', phoneNumber: '+15551234567' },
      receivers: [
        { receiverId: 'r1', receiverName: 'Receiver One', amount: 1000 },
        { receiverId: 'r2', receiverName: 'Receiver Two', amount: 2000 },
      ],
    };

    const results = await worker.runUntil(
      client.workflow.execute(processTransfers, {
        args: [request],
        workflowId: 'test-integration-all-success',
        taskQueue,
      }),
    );

    assert.equal(results.length, 2);
    assert.equal(results[0].status, 'success');
    assert.equal(results[1].status, 'success');
    assert.equal(results[0].attempts, 1);
    assert.equal(results[1].attempts, 1);
  });
});
