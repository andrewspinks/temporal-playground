import { ApplicationFailure, Context } from '@temporalio/activity';
import type { SimulatedError } from './types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR, INTERMITTENT_PAYMENT_ERROR } from './types';

export async function processPayment(
  accountId: string,
  receiverId: string,
  amount: number,
  simulateError?: SimulatedError,
  succeedAfterAttempts?: number,
  // For user errors: the workflow passes its own retry counter (day 1..14) because
  // each daily retry is a fresh activity execution and Temporal's attempt resets to 1.
  workflowAttempt?: number,
): Promise<{ transactionId: string; attempt: number }> {
  console.log(`Payment system charge: account=${accountId}, receiver=${receiverId}, amount=${amount}`);

  if (simulateError === 'non-retryable') {
    throw ApplicationFailure.create({
      message: 'Card expired',
      type: NON_RETRYABLE_PAYMENT_ERROR,
      nonRetryable: true,
    });
  }

  if (simulateError === 'user-error') {
    // Fall back to the activity's own attempt counter so simulation works whether
    // the workflow drives retries manually (workflowAttempt) or via Temporal's
    // retry policy (Context.current().info.attempt).
    const attempt = workflowAttempt ?? Context.current().info.attempt;
    if (!succeedAfterAttempts || attempt <= succeedAfterAttempts) {
      throw ApplicationFailure.create({
        message: 'Insufficient funds',
        type: USER_PAYMENT_ERROR,
        // nonRetryable: false lets the proxy's nonRetryableErrorTypes decide.
        // Approaches 1–3 list USER_PAYMENT_ERROR there; approach 4's daily proxy does not.
        nonRetryable: false,
      });
    }
  }

  if (simulateError === 'intermittent') {
    // Context.current().info.attempt is 1-based and increments with each Temporal retry.
    const attempt = Context.current().info.attempt;
    if (!succeedAfterAttempts || attempt <= succeedAfterAttempts) {
      throw ApplicationFailure.create({
        message: 'Network timeout',
        type: INTERMITTENT_PAYMENT_ERROR,
        nonRetryable: false,
      });
    }
  }

  return { transactionId: `txn_${accountId}_${receiverId}_${Date.now()}`, attempt: Context.current().info.attempt };
}

export async function sendSmsNotification(phoneNumber: string, message: string): Promise<void> {
  console.log(`SMS to ${phoneNumber}: ${message}`);
}
