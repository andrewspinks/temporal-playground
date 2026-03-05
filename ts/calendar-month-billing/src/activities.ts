import { log } from '@temporalio/activity';
import { Client, MONTHS } from '@temporalio/client';
import { nextBillingDate } from './billing-helpers';

export async function generateInvoice(customerId: string, billingMonth: string): Promise<string> {
  const invoiceId = `inv-${customerId}-${billingMonth}-${Date.now()}`;
  log.info('Generating invoice', { customerId, billingMonth, invoiceId });
  return invoiceId;
}

/**
 * Factory: creates activities that require an injected Temporal Client.
 * Used by approach 2 (self-reschedule) and approach 4 (chain+startDelay).
 */
export function createBillingActivities(client: Client) {
  return {
    /**
     * Approach 2: update the billing schedule to fire on the exact last day of next month.
     * Replaces the schedule spec with a pinned one-time calendar entry.
     */
    async rescheduleToNextMonth(scheduleId: string): Promise<void> {
      const next = nextBillingDate(new Date(), 9);
      log.info('Rescheduling billing to next last-day-of-month', {
        scheduleId,
        nextDate: next.toISOString(),
      });
      const handle = client.schedule.getHandle(scheduleId);
      await handle.update((prev) => ({
        // Spread the existing description (carries over action, state, policies, etc.)
        ...prev,
        spec: {
          calendars: [
            {
              comment: `Billing – dynamically updated for ${next.toISOString().slice(0, 10)}`,
              year: next.getUTCFullYear(),
              month: MONTHS[next.getUTCMonth()], // 'JANUARY' … 'DECEMBER'
              dayOfMonth: next.getUTCDate(),
              hour: next.getUTCHours(),
            },
          ],
        },
      }));
    },

    /**
     * Approach 4: start the next billing workflow with a server-side startDelay.
     * No TIMER_STARTED event is recorded — the delay is handled entirely server-side.
     */
    async startNextBillingCycle(customerId: string, nextRunDate: string, delayMs: number): Promise<void> {
      const workflowId = `billing-chain-${customerId}-${nextRunDate.slice(0, 10)}`;
      log.info('Chaining next billing cycle', { customerId, workflowId, delayMs });
      await client.workflow.start('billingChainWorkflow', {
        taskQueue: 'schedules',
        workflowId,
        args: [customerId],
        startDelay: delayMs,
      });
    },
  };
}
