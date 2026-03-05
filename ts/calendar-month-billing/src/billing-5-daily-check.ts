/**
 * Approach 5: Hybrid calendar + workflow-side day check
 *
 * For billingDay <= 28: a single spec fires on exactly that day every month — no checks.
 *
 * For billingDay 29–31: all months except February get static per-month-group specs
 * (like approach 1) that fire on exactly the right day — no checks, no no-ops.
 * February alone needs the daily-check treatment because its length varies between
 * 28 (non-leap) and 29 (leap) days. Two February specs are created (days 28 and 29);
 * the workflow skips whichever isn't the effective billing day.
 *
 * Result: at most 1 no-op per 4 years (Feb 28 in a leap year when billingDay ≥ 29),
 * down from up to 3 no-ops every month with the naive daily-check approach.
 *
 * Trade-offs:
 *   + Full Schedule UI (pause, backfill, describe, list)
 *   + Correct for any billing day, including end-of-month edge cases
 *   + Simple: no circular dependencies, no chaining, no continueAsNew
 *   - One no-op workflow start every ~4 years (Feb 28 in a leap year, billingDay ≥ 29)
 *
 * Actions/cycle: 2 per real run; +2 no-op once every ~4 years (leap year Feb only)
 */
import { Connection, Client, ScheduleOverlapPolicy, CalendarSpec } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { billingDailyCheckWorkflow } from './workflows';

const CUSTOMER_ID = 'cust-001';
const BILLING_DAY = 31; // 1–31: desired billing day; capped to last day of month when needed
const SCHEDULE_ID = `billing-daily-check-${CUSTOMER_ID}`;

type MonthName = (typeof MONTH_NAMES)[number];
const MONTH_NAMES = [
  'JANUARY',
  'FEBRUARY',
  'MARCH',
  'APRIL',
  'MAY',
  'JUNE',
  'JULY',
  'AUGUST',
  'SEPTEMBER',
  'OCTOBER',
  'NOVEMBER',
  'DECEMBER',
] as const;

// Fixed last day per month (non-leap year value for February)
const MONTH_MAX_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * Build CalendarSpec entries for the hybrid approach.
 *
 * For billingDay <= 28: a single spec fires on exactly that day every month.
 * For billingDay 29–31: non-February months are grouped by their fixed effective day
 * (like approach 1 — no workflow check needed). February gets two specs (days 28 and 29)
 * so the workflow can handle the leap-year vs non-leap-year difference at runtime.
 */
function buildSpecs(billingDay: number, hour = 9): CalendarSpec[] {
  if (billingDay <= 28) {
    return [{ comment: `Billing day ${billingDay} — exact, no check needed`, dayOfMonth: billingDay, hour }];
  }

  const specs: CalendarSpec[] = [];

  // Group non-February months by their effective billing day (always fixed)
  const groups = new Map<number, MonthName[]>();
  for (let i = 0; i < 12; i++) {
    if (i === 1) continue; // February handled separately below
    const effectiveDay = Math.min(billingDay, MONTH_MAX_DAYS[i]);
    if (!groups.has(effectiveDay)) groups.set(effectiveDay, []);
    groups.get(effectiveDay)!.push(MONTH_NAMES[i]);
  }
  for (const [day, months] of groups) {
    specs.push({ comment: `${months.join(', ')} — exact day ${day}`, month: months, dayOfMonth: day, hour });
  }

  // February: day 28 fires every year; day 29 fires only in leap years (schedule skips
  // non-existent dates). The workflow checks which is the effective billing day.
  specs.push({
    comment: 'FEBRUARY day 28 — effective billing day in non-leap years',
    month: ['FEBRUARY'],
    dayOfMonth: 28,
    hour,
  });
  specs.push({
    comment: 'FEBRUARY day 29 — effective billing day in leap years',
    month: ['FEBRUARY'],
    dayOfMonth: 29,
    hour,
  });

  return specs;
}

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  const specs = buildSpecs(BILLING_DAY);

  const schedule = await client.schedule.create({
    scheduleId: SCHEDULE_ID,
    action: {
      type: 'startWorkflow',
      workflowType: billingDailyCheckWorkflow,
      args: [CUSTOMER_ID, BILLING_DAY],
      taskQueue: 'schedules',
    },
    policies: {
      overlap: ScheduleOverlapPolicy.SKIP,
      catchupWindow: '1 day',
    },
    spec: { calendars: specs },
  });

  console.log(`Created schedule '${schedule.scheduleId}'.`);
  console.log(`Billing day: ${BILLING_DAY} (capped to last day of month when needed).`);
  if (BILLING_DAY > 28) {
    console.log(`Non-Feb months: static specs, zero no-ops. February: 1 no-op every ~4 years (leap year only).`);
  }
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
