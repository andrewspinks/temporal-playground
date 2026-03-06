/**
 * Approach 4: Flat workflow — activity-level retry policy for daily retries.
 *
 * No child workflows. No sleep() loops. Temporal's server manages the wait between
 * daily retries entirely server-side; those retries add zero events to workflow history
 * regardless of how many occur.
 *
 * Two proxy configs for the same processPayment activity:
 *
 *   tryPaymentFast  — fast intermittent retries; USER_PAYMENT_ERROR and
 *                     NON_RETRYABLE_PAYMENT_ERROR fail immediately (non-retryable
 *                     in nonRetryableErrorTypes), surfacing to workflow logic.
 *
 *   tryPaymentDaily — daily retries for user errors; only NON_RETRYABLE_PAYMENT_ERROR
 *                     is blocked. USER_PAYMENT_ERROR is NOT in nonRetryableErrorTypes,
 *                     so Temporal retries it on the configured 1-day interval.
 *
 * Trade-off: the workflow is dormant while the activity is retrying, so it cannot
 * send an SMS between each daily attempt. Instead, one upfront SMS is sent when the
 * user error is first detected, and a final SMS is sent on success or exhaustion.
 */

import { proxyActivities, ActivityFailure, ApplicationFailure } from '@temporalio/workflow';
import type * as activities from './activities';
import type { TransferRequest, TransferResult, AccountInfo, ReceiverTransfer } from './types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR } from './types';

const MAX_DAILY_RETRIES = 14;
const RETRY_INTERVAL = '1 min'; // simulates 1 day; change to '1 day' for production

// Phase 1: fast retries for intermittent errors only.
// User errors and non-retryable errors are not retried here — they surface to the workflow.
const { processPayment: tryPaymentFast } = proxyActivities<typeof activities>({
  startToCloseTimeout: '30 seconds',
  retry: {
    initialInterval: '1 second',
    backoffCoefficient: 2,
    maximumInterval: '30 seconds',
    maximumAttempts: 10,
    nonRetryableErrorTypes: [NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR],
  },
});

// Phase 2: daily retries managed by Temporal's server.
// USER_PAYMENT_ERROR is intentionally absent from nonRetryableErrorTypes so the server
// retries it. NON_RETRYABLE_PAYMENT_ERROR still stops immediately (card escalation).
// scheduleToCloseTimeout covers MAX_DAILY_RETRIES × RETRY_INTERVAL + buffer.
// In production with RETRY_INTERVAL = '1 day': set to '15 days'.
const { processPayment: tryPaymentDaily } = proxyActivities<typeof activities>({
  startToCloseTimeout: '30 seconds',
  scheduleToCloseTimeout: '20 min', // production: '15 days'
  retry: {
    initialInterval: RETRY_INTERVAL,
    backoffCoefficient: 1,
    maximumAttempts: MAX_DAILY_RETRIES,
    nonRetryableErrorTypes: [NON_RETRYABLE_PAYMENT_ERROR],
  },
});

const { sendSmsNotification } = proxyActivities<typeof activities>({
  startToCloseTimeout: '10 seconds',
  retry: {
    initialInterval: '1 second',
    backoffCoefficient: 2,
    maximumInterval: '10 seconds',
    maximumAttempts: 5,
  },
});

/** Process monthly transfers for a single account to 1–3 receivers. */
export async function processTransfers(request: TransferRequest): Promise<TransferResult[]> {
  return Promise.all(request.receivers.map((receiver) => processReceiverTransfer(request.account, receiver)));
}

async function processReceiverTransfer(account: AccountInfo, receiver: ReceiverTransfer): Promise<TransferResult> {
  // Phase 1: fast attempt. Handles intermittent errors via built-in retries.
  // User and non-retryable errors surface immediately.
  try {
    await tryPaymentFast(account.accountId, receiver.receiverId, receiver.amount, receiver.simulateError, receiver.succeedAfterAttempts);
    return { receiverId: receiver.receiverId, receiverName: receiver.receiverName, status: 'success', attempts: 1 };
  } catch (err) {
    const type = extractErrorType(err);

    if (type === NON_RETRYABLE_PAYMENT_ERROR) {
      return handleNonRetryable(account, receiver, err, 1);
    }

    if (type !== USER_PAYMENT_ERROR) {
      // Intermittent retries exhausted — treat as non-retryable
      return handleNonRetryable(account, receiver, err, 1);
    }
  }

  // Phase 2: user payment error detected. Notify once upfront, then hand off to
  // Temporal's retry policy. The workflow sleeps here — no loop, no timer events.
  await sendSmsNotification(
    account.phoneNumber,
    `Your transfer of $${(receiver.amount / 100).toFixed(2)} to ${receiver.receiverName} failed. We'll retry daily for up to ${MAX_DAILY_RETRIES} days.`,
  );

  try {
    // The activity returns Context.current().info.attempt (its Temporal retry counter),
    // so we can report exactly how many daily attempts were made.
    const { attempt: dailyAttempt } = await tryPaymentDaily(account.accountId, receiver.receiverId, receiver.amount, receiver.simulateError, receiver.succeedAfterAttempts);
    await sendSmsNotification(
      account.phoneNumber,
      `Good news: your transfer to ${receiver.receiverName} has been processed successfully.`,
    );
    return { receiverId: receiver.receiverId, receiverName: receiver.receiverName, status: 'success', attempts: 1 + dailyAttempt };
  } catch (err) {
    const type = extractErrorType(err);

    if (type === NON_RETRYABLE_PAYMENT_ERROR) {
      // Card escalated from insufficient funds to expired during the retry window.
      return handleNonRetryable(account, receiver, err, MAX_DAILY_RETRIES + 1);
    }

    // USER_PAYMENT_ERROR: tryPaymentDaily exhausted all retries.
    await sendSmsNotification(
      account.phoneNumber,
      `Your transfer to ${receiver.receiverName} could not be processed after ${MAX_DAILY_RETRIES} daily attempts.`,
    );
    return {
      receiverId: receiver.receiverId,
      receiverName: receiver.receiverName,
      status: 'failed',
      reason: `Exhausted ${MAX_DAILY_RETRIES} daily retries`,
      attempts: MAX_DAILY_RETRIES + 1,
    };
  }
}

async function handleNonRetryable(
  account: AccountInfo,
  receiver: ReceiverTransfer,
  err: unknown,
  attempts: number,
): Promise<TransferResult> {
  const reason = err instanceof Error ? err.message : 'Payment declined';
  await sendSmsNotification(
    account.phoneNumber,
    `Action required: your transfer to ${receiver.receiverName} was declined. Please update your payment method.`,
  );
  return { receiverId: receiver.receiverId, receiverName: receiver.receiverName, status: 'flagged', reason, attempts };
}

function extractErrorType(err: unknown): string | undefined {
  if (err instanceof ActivityFailure && err.cause instanceof ApplicationFailure) {
    return err.cause.type ?? undefined;
  }
  if (err instanceof ApplicationFailure) {
    return err.type ?? undefined;
  }
  return undefined;
}
