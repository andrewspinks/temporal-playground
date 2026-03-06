import {
  proxyActivities,
  sleep,
  ActivityFailure,
  ApplicationFailure,
  executeChild,
  workflowInfo,
} from '@temporalio/workflow';
import type * as activities from './activities';
import type { TransferRequest, TransferResult, AccountInfo, ReceiverTransfer } from './types';
import { NON_RETRYABLE_PAYMENT_ERROR, USER_PAYMENT_ERROR } from './types';

const MAX_DAILY_RETRIES = 14;

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
 * Each child is independently visible in the Temporal UI with its own event history.
 */
export async function processTransfersWithChildren(request: TransferRequest): Promise<TransferResult[]> {
  const parentId = workflowInfo().workflowId;
  return Promise.all(
    request.receivers.map((receiver) =>
      executeChild(processReceiverTransfer, {
        args: [request.account, receiver],
        workflowId: `${parentId}/receiver-${receiver.receiverId}`,
      }),
    ),
  );
}

/**
 * Child workflow: handles the full lifecycle of a single receiver transfer,
 * including error classification and the 14-day retry loop for user errors.
 */
export async function processReceiverTransfer(account: AccountInfo, receiver: ReceiverTransfer): Promise<TransferResult> {
  try {
    await processPayment(
      account.accountId,
      receiver.receiverId,
      receiver.amount,
      receiver.simulateError,
      receiver.succeedAfterAttempts,
      1,
    );
    return { receiverId: receiver.receiverId, receiverName: receiver.receiverName, status: 'success', attempts: 1 };
  } catch (err) {
    const type = extractErrorType(err);

    if (type === NON_RETRYABLE_PAYMENT_ERROR) {
      return handleNonRetryable(account, receiver, err, 1);
    }

    if (type === USER_PAYMENT_ERROR) {
      return handleUserErrorWithDailyRetry(account, receiver);
    }

    // Intermittent retries exhausted by Temporal — treat as non-retryable
    return handleNonRetryable(account, receiver, err, 1);
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

async function handleUserErrorWithDailyRetry(account: AccountInfo, receiver: ReceiverTransfer): Promise<TransferResult> {
  await sendSmsNotification(
    account.phoneNumber,
    `Your transfer of $${(receiver.amount / 100).toFixed(2)} to ${receiver.receiverName} failed. We'll retry tomorrow.`,
  );

  for (let day = 1; day <= MAX_DAILY_RETRIES; day++) {
    await sleep('1 min');

    try {
      await processPayment(
        account.accountId,
        receiver.receiverId,
        receiver.amount,
        receiver.simulateError,
        receiver.succeedAfterAttempts,
        day + 1,
      );
      return {
        receiverId: receiver.receiverId,
        receiverName: receiver.receiverName,
        status: 'success',
        attempts: day + 1,
      };
    } catch (err) {
      const type = extractErrorType(err);

      if (type === NON_RETRYABLE_PAYMENT_ERROR) {
        return handleNonRetryable(account, receiver, err, day + 1);
      }

      if (type === USER_PAYMENT_ERROR) {
        if (day < MAX_DAILY_RETRIES) {
          await sendSmsNotification(
            account.phoneNumber,
            `Your transfer to ${receiver.receiverName} failed again. Retrying tomorrow (attempt ${day + 1} of ${MAX_DAILY_RETRIES}).`,
          );
        }
        continue;
      }

      // Intermittent retries exhausted during retry window
      return handleNonRetryable(account, receiver, err, day + 1);
    }
  }

  await sendSmsNotification(
    account.phoneNumber,
    `Your transfer to ${receiver.receiverName} could not be processed this month after ${MAX_DAILY_RETRIES} attempts.`,
  );
  return {
    receiverId: receiver.receiverId,
    receiverName: receiver.receiverName,
    status: 'failed',
    reason: `Exhausted ${MAX_DAILY_RETRIES} daily retries`,
    attempts: MAX_DAILY_RETRIES + 1,
  };
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
