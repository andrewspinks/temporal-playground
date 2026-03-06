export const NON_RETRYABLE_PAYMENT_ERROR = 'NonRetryablePaymentError';
export const USER_PAYMENT_ERROR = 'UserPaymentError';
export const INTERMITTENT_PAYMENT_ERROR = 'IntermittentPaymentError';

export type SimulatedError = 'non-retryable' | 'user-error' | 'intermittent';

export interface ReceiverTransfer {
  receiverId: string;
  receiverName: string;
  amount: number; // in cents
  /** If set, the mock activity will throw this error type instead of succeeding. */
  simulateError?: SimulatedError;
  /**
   * When combined with simulateError, fail for this many attempts then succeed.
   * For intermittent errors this counts Temporal-level retries; for user errors it
   * counts workflow-level daily retries. Omit to fail permanently.
   */
  succeedAfterAttempts?: number;
}

export interface AccountInfo {
  accountId: string;
  phoneNumber: string;
}

export interface TransferRequest {
  account: AccountInfo;
  receivers: ReceiverTransfer[]; // 1–3 items
}

export type TransferStatus = 'success' | 'flagged' | 'failed';

export interface TransferResult {
  receiverId: string;
  receiverName: string;
  status: TransferStatus;
  reason?: string;
  attempts: number;
}
