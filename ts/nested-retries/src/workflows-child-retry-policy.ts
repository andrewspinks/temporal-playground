import {
  proxyActivities,
  ActivityFailure,
  ApplicationFailure,
  executeChild,
  workflowInfo,
} from '@temporalio/workflow';
import type * as activities from './activities';
import type { TransferRequest, TransferResult, AccountInfo, ReceiverTransfer } from './types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR } from './types';

const MAX_DAILY_RETRIES = 14;
const RETRY_INTERVAL = '1 min'; // simulates 1 day; change to '1 day' for production

const { processPayment } = proxyActivities<typeof activities>({
  startToCloseTimeout: '30 seconds',
  retry: {
    initialInterval: '1 second',
    backoffCoefficient: 2,
    maximumInterval: '30 seconds',
    maximumAttempts: 10,
    nonRetryableErrorTypes: [NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR],
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

/**
 * Parent workflow: starts a child workflow per receiver and runs them in parallel.
 * Temporal manages the 14-day retry schedule via the retry policy on executeChild.
 * Each retry is a new workflow run — separately visible in the Temporal UI.
 */
export async function processTransfersWithRetryPolicy(request: TransferRequest): Promise<TransferResult[]> {
  const parentId = workflowInfo().workflowId;
  return Promise.all(
    request.receivers.map(async (receiver) => {
      try {
        return await executeChild(processReceiverTransfer, {
          args: [request.account, receiver],
          workflowId: `${parentId}/receiver-${receiver.receiverId}`,
          retry: {
            initialInterval: RETRY_INTERVAL,
            backoffCoefficient: 1,
            maximumInterval: RETRY_INTERVAL,
            maximumAttempts: MAX_DAILY_RETRIES + 1,
          },
        });
      } catch (err) {
        // ChildWorkflowFailure: child exhausted all retries; final SMS already sent by child
        return {
          receiverId: receiver.receiverId,
          receiverName: receiver.receiverName,
          status: 'failed' as const,
          reason: `Exhausted ${MAX_DAILY_RETRIES} daily retries`,
          attempts: MAX_DAILY_RETRIES + 1,
        };
      }
    }),
  );
}

/**
 * Child workflow: handles a single receiver transfer attempt.
 * workflowInfo().attempt increments with each Temporal retry (1 → MAX_DAILY_RETRIES + 1).
 * USER_PAYMENT_ERROR throws to trigger a Temporal-managed retry the next day.
 * NON_RETRYABLE returns normally — no throw, no retry.
 */
export async function processReceiverTransfer(account: AccountInfo, receiver: ReceiverTransfer): Promise<TransferResult> {
  const attempt = workflowInfo().attempt;
  try {
    await processPayment(
      account.accountId,
      receiver.receiverId,
      receiver.amount,
      receiver.simulateError,
      receiver.succeedAfterAttempts,
      attempt,
    );
    return { receiverId: receiver.receiverId, receiverName: receiver.receiverName, status: 'success', attempts: attempt };
  } catch (err) {
    const type = extractErrorType(err);

    if (type === NON_RETRYABLE_PAYMENT_ERROR) {
      return handleNonRetryable(account, receiver, err, attempt);
    }

    if (type === USER_PAYMENT_ERROR) {
      const isLast = attempt >= MAX_DAILY_RETRIES + 1;
      await sendSmsNotification(
        account.phoneNumber,
        isLast
          ? `Your transfer to ${receiver.receiverName} could not be processed this month after ${MAX_DAILY_RETRIES} attempts.`
          : `Your transfer of $${(receiver.amount / 100).toFixed(2)} to ${receiver.receiverName} failed. We'll retry tomorrow.`,
      );
      throw ApplicationFailure.create({ message: 'User payment error, retrying tomorrow', nonRetryable: false });
    }

    // Intermittent retries exhausted by Temporal — treat as non-retryable
    return handleNonRetryable(account, receiver, err, attempt);
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
