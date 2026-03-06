import { MockActivityEnvironment } from '@temporalio/testing';
import { describe, it } from 'mocha';
import assert from 'assert';
import * as activities from '../activities';

describe('processPayment', () => {
  it('returns a transaction ID on success', async () => {
    const env = new MockActivityEnvironment();
    const result = await env.run(activities.processPayment, 'account-1', 'receiver-1', 5000);
    assert.ok((result as { transactionId: string }).transactionId.startsWith('txn_account-1_receiver-1_'));
  });
});

describe('sendSmsNotification', () => {
  it('completes without error', async () => {
    const env = new MockActivityEnvironment();
    await env.run(activities.sendSmsNotification, '+15551234567', 'Test message');
  });
});
