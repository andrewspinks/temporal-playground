/**
 * Approach 2: Self-reschedule via Schedule Update
 *
 * Creates a Schedule that fires once (immediately, for testing). After each billing run,
 * the workflow calls the `rescheduleToNextMonth` activity, which updates the schedule spec
 * to the exact last day of next month. Precise end-of-month, still a Schedule entity.
 *
 * Trade-offs:
 *   + Full Schedule UI (pause, backfill, describe, list)
 *   + Precise last-day-of-month (computed at runtime)
 *   - Circular dependency: workflow knows its own schedule ID
 *   - Extra activity per cycle (reschedule call)
 *   - Partial-failure risk: billing succeeds but reschedule fails → schedule goes stale
 *
 * Actions/cycle: 6  (2 schedule trigger + 1 WF start + 2 activities + 1 reschedule activity)
 */
import { Connection, Client, ScheduleOverlapPolicy, MONTHS } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { billingSelfRescheduleWorkflow } from './workflows';
import { nextBillingDate } from './billing-helpers';

const CUSTOMER_ID = 'cust-001';
const SCHEDULE_ID = `billing-self-reschedule-${CUSTOMER_ID}`;

async function run() {
  const config = loadClientConnectConfig();
  const connection = await Connection.connect(config.connectionOptions);
  const client = new Client({ connection });

  // Compute the first real billing date (last day of next month)
  const firstRun = nextBillingDate(new Date(), 9);

  const schedule = await client.schedule.create({
    scheduleId: SCHEDULE_ID,
    action: {
      type: 'startWorkflow',
      workflowType: billingSelfRescheduleWorkflow,
      // Pass the schedule ID so the workflow can update it after billing
      args: [CUSTOMER_ID, SCHEDULE_ID],
      taskQueue: 'schedules',
    },
    policies: {
      overlap: ScheduleOverlapPolicy.SKIP,
      catchupWindow: '1 day',
    },
    spec: {
      // Pin to the exact last day of next month. The workflow will update this after each run.
      calendars: [
        {
          comment: `Initial billing date — workflow updates this after each run`,
          year: firstRun.getUTCFullYear(),
          month: MONTHS[firstRun.getUTCMonth()], // 'JANUARY' … 'DECEMBER'
          dayOfMonth: firstRun.getUTCDate(),
          hour: firstRun.getUTCHours(),
        },
      ],
    },
  });

  console.log(`Created schedule '${schedule.scheduleId}'.`);
  console.log(`First run: ${firstRun.toISOString()} (last day of next month)`);
  console.log('After each run the workflow updates the spec to the following last-day-of-month.');
  console.log('\nTo trigger immediately for testing:');
  console.log(`  temporal schedule trigger --schedule-id ${SCHEDULE_ID}`);
  console.log('\nUseful commands:');
  console.log(`  temporal schedule describe --schedule-id ${SCHEDULE_ID}`);
  console.log(`  temporal schedule delete   --schedule-id ${SCHEDULE_ID}`);

  await connection.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
