/**
 * Approach 1: Static calendar schedule
 *
 * Creates a Schedule with CalendarSpec entries that fire on a given billing day
 * each month. Months shorter than the billing day are capped to their last day
 * (February is always capped at 28 to guarantee exactly one run per month).
 *
 * Trade-offs:
 *   + Full Schedule UI (pause, backfill, describe, list)
 *   + Zero workflow complexity
 *   - February always fires on the 28th (even in leap years when billing day > 28)
 *   - Static spec — can't adapt to runtime business logic
 */
import { Connection, Client, ScheduleOverlapPolicy, CalendarSpec } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { billingCalendarWorkflow } from './workflows';

const CUSTOMER_ID = 'cust-001';
const BILLING_DAY = 31; // 1–31: the desired billing day of each month
const SCHEDULE_ID = `billing-calendar-${CUSTOMER_ID}`;

type MonthName = typeof MONTH_NAMES[number];

const MONTH_NAMES = [
  'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
  'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
] as const;

// Max days per month (Feb capped at 28 to avoid leap-year double-billing)
const MAX_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * Build CalendarSpec entries for a billing day. Months are grouped by their
 * effective day: min(billingDay, maxDaysInMonth). For billingDay <= 28 this
 * produces a single spec; for 31 it produces three (31-day, 30-day, Feb).
 */
function buildCalendarSpecs(billingDay: number, hour = 9): CalendarSpec[] {
  const groups = new Map<number, MonthName[]>();
  for (let i = 0; i < 12; i++) {
    const effectiveDay = Math.min(billingDay, MAX_DAYS[i]);
    if (!groups.has(effectiveDay)) groups.set(effectiveDay, []);
    groups.get(effectiveDay)!.push(MONTH_NAMES[i]);
  }

  return Array.from(groups.entries()).map(([day, months]) => ({
    comment: months.length === 12
      ? `All months on day ${day}`
      : `${months.join(', ')} on day ${day}`,
    month: months,
    dayOfMonth: day,
    hour,
  }));
}

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  const schedule = await client.schedule.create({
    scheduleId: SCHEDULE_ID,
    action: {
      type: 'startWorkflow',
      workflowType: billingCalendarWorkflow,
      args: [CUSTOMER_ID],
      taskQueue: 'schedules',
    },
    policies: {
      overlap: ScheduleOverlapPolicy.SKIP,
      catchupWindow: '1 day',
    },
    spec: {
      calendars: buildCalendarSpecs(BILLING_DAY),
    },
  });

  console.log(`Created schedule '${schedule.scheduleId}'.`);
  console.log(`Fires on day ${BILLING_DAY} of each month at 09:00 UTC (capped to month length).`);
  console.log('\nUseful commands:');
  console.log(`  temporal schedule describe --schedule-id ${SCHEDULE_ID}`);
  console.log(`  temporal schedule trigger  --schedule-id ${SCHEDULE_ID}   # trigger now for testing`);
  console.log(`  temporal schedule delete   --schedule-id ${SCHEDULE_ID}`);

  await connection.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
