import { proxyActivities, sleep, continueAsNew, log } from '@temporalio/workflow';
import { nextBillingDate, lastDayOfMonth } from './billing-helpers';

// Client-injected activities (approaches 2 & 4) — typed inline to avoid importing
// billing-activities.ts (which imports @temporalio/client) into the workflow sandbox.
type BillingClientActivities = {
  rescheduleToNextMonth(scheduleId: string): Promise<void>;
  startNextBillingCycle(customerId: string, nextRunDate: string, delayMs: number): Promise<void>;
  generateInvoice(customerId: string, billingMonth: string): Promise<string>;
};

const { rescheduleToNextMonth, startNextBillingCycle, generateInvoice } = proxyActivities<BillingClientActivities>({
  startToCloseTimeout: '1 minute',
});

// ─── Approach 1: Static calendar schedule ──────────────────────────────────
// The schedule has 4 calendar specs covering every last-day-of-month.
// The workflow itself is trivial — all scheduling logic lives in the schedule spec.

export async function billingCalendarWorkflow(customerId: string): Promise<void> {
  const billingMonth = new Date().toISOString().slice(0, 7); // e.g. "2026-03"
  await generateInvoice(customerId, billingMonth);
}

// ─── Approach 2: Self-reschedule via Schedule Update ──────────────────────
// After billing, the workflow updates its own schedule spec to the exact
// last day of next month. Precise end-of-month, still a Schedule entity.

export async function billingSelfRescheduleWorkflow(customerId: string, scheduleId: string): Promise<void> {
  const billingMonth = new Date().toISOString().slice(0, 7);
  await generateInvoice(customerId, billingMonth);
  await rescheduleToNextMonth(scheduleId);
}

// ─── Approach 3: continueAsNew + sleep ────────────────────────────────────
// Bill → sleep until last-day-of-next-month → continueAsNew.
// No schedule entity. Each month is the same workflow ID / different run ID.

export async function billingContinueAsNewWorkflow(customerId: string): Promise<void> {
  const billingMonth = new Date().toISOString().slice(0, 7);
  await generateInvoice(customerId, billingMonth);

  const next = nextBillingDate(new Date(), 9);
  const delayMs = next.getTime() - Date.now();
  await sleep(delayMs);

  await continueAsNew<typeof billingContinueAsNewWorkflow>(customerId);
}

// ─── Approach 4: Self-chaining via startDelay ─────────────────────────────
// Bill → activity starts a brand-new workflow execution with server-side startDelay.
// No TIMER_STARTED event recorded. Each cycle is a fully independent execution.

export async function billingChainWorkflow(customerId: string): Promise<void> {
  const billingMonth = new Date().toISOString().slice(0, 7);
  await generateInvoice(customerId, billingMonth);

  const next = nextBillingDate(new Date(), 9);
  const delayMs = next.getTime() - Date.now();
  await startNextBillingCycle(customerId, next.toISOString(), delayMs);
}

// ─── Approach 5: Daily schedule + workflow-side day check ─────────────────
// Schedule fires on days 28–billingDay each month. The workflow checks whether
// today matches the effective billing day (billingDay capped to last day of month)
// and exits early if not. For billingDay <= 28, the schedule fires exactly once
// per month so no early-exit is ever needed.

export async function billingDailyCheckWorkflow(customerId: string, billingDay: number): Promise<void> {
  const now = new Date();
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth() + 1;
  const today = now.getUTCDate();
  const effectiveDay = Math.min(billingDay, lastDayOfMonth(year, month));

  if (today !== effectiveDay) {
    log.info('Skipping: not the effective billing day', { today, effectiveDay, billingDay });
    return;
  }

  const billingMonth = now.toISOString().slice(0, 7);
  await generateInvoice(customerId, billingMonth);
}
