# Monthly Billing: Five Temporal Scheduling Approaches

Explores five ways to run billing on a configurable billing day each month (capped to the last day of the month when needed). Each approach is a different trade-off between observability, precision, cost, and complexity.

**Key challenge:** Temporal's calendar spec has no native "last day of month" expression. `dayOfMonth: 31` silently skips months that don't have 31 days.

---

## Approach 1 — Static Calendar Schedule

**File:** `src/billing-1-calendar-schedule.ts`
**Workflow:** `billingCalendarWorkflow`

Creates a Schedule with 4 `CalendarSpec` entries covering every last-day-of-month:

| Spec | Months | Day |
|------|--------|-----|
| 31-day months | Jan, Mar, May, Jul, Aug, Oct, Dec | 31 |
| 30-day months | Apr, Jun, Sep, Nov | 30 |
| February (every year) | Feb | 28 |

Creates a Schedule with CalendarSpec entries that fire on a given billing day each month. Months shorter than the billing day are capped to their last day (February is always capped at 28 to guarantee exactly one run per month).

**Actions/cycle: 5**
| Event | Count |
|-------|-------|
| Schedule trigger | 2 |
| Workflow start | 1 |
| Activities (`generateInvoice` + `chargeCustomer`) | 2 |
| **Total** | **5** |

**Pros**
- Full Schedule UI: pause, backfill, describe, list
- Zero workflow complexity — the workflow is just two activity calls
- Most observable approach

**Cons**
- February always fires on the 28th (even in leap years when billing day > 28)
- Static spec — can't adapt to runtime business logic

---

## Approach 2 — Self-Reschedule via Schedule Update

**File:** `src/billing-2-self-reschedule.ts`
**Workflow:** `billingSelfRescheduleWorkflow`

A Schedule fires the workflow. After billing completes, the workflow calls `rescheduleToNextMonth` — an activity that updates the schedule's spec to the exact last day of next month (computed at runtime).

**Actions/cycle: 6**
| Event | Count |
|-------|-------|
| Schedule trigger | 2 |
| Workflow start | 1 |
| Activities (`generateInvoice` + `chargeCustomer`) | 2 |
| Reschedule activity | 1 |
| **Total** | **6** |

**Pros**
- Full Schedule UI: pause, backfill, describe, list
- Precise last-day-of-month (computed at runtime, not hardcoded)
- Adaptable — the reschedule activity can incorporate business logic

**Cons**
- Circular dependency: the workflow knows its own schedule ID
- One extra action per cycle (the reschedule activity)
- Partial-failure risk: billing succeeds but reschedule activity fails → schedule goes stale

---

## Approach 3 — `continueAsNew` + `sleep`

**File:** `src/billing-3-continue-as-new.ts`
**Workflow:** `billingContinueAsNewWorkflow`

A single long-lived workflow: bill → compute next last-day-of-month → `sleep` until then → `continueAsNew`. No Schedule entity at all. Each `continueAsNew` starts a fresh execution under the same workflow ID.

**Actions/cycle: 4**
| Event | Count |
|-------|-------|
| `continueAsNew` (also serves as the "restart") | 1 |
| Activities (`generateInvoice` + `chargeCustomer`) | 2 |
| Timer (`sleep`) | 1 |
| **Total** | **4** |

**Pros**
- Cheapest: fewest actions per cycle
- Precise last-day-of-month
- Self-contained: no schedule infrastructure needed
- History stays clean via `continueAsNew`

**Cons**
- Not visible in Schedules UI
- No native pause/backfill — must cancel and restart the workflow
- Monitoring across cycles requires tracking the workflow ID (each `continueAsNew` is a new run)

---

## Approach 4 — Self-Chaining via `startDelay`

**File:** `src/billing-4-chain-start-delay.ts`
**Workflow:** `billingChainWorkflow`

After billing, an activity starts a **brand-new workflow execution** with `startDelay` set to the milliseconds until the next last-day-of-month. The delay is handled server-side — no `TIMER_STARTED` event is recorded, saving one action vs approach 3.

**Actions/cycle: 4**
| Event | Count |
|-------|-------|
| Workflow start | 1 |
| Activities (`generateInvoice` + `chargeCustomer`) | 2 |
| Chain activity (starts next workflow) | 1 |
| `startDelay` timer | 0 — handled server-side, no event |
| **Total** | **4** |

**Pros**
- Tied for cheapest: `startDelay` is free (no timer event)
- Precise last-day-of-month
- Clean per-cycle history — each billing run is a completely independent execution

**Cons**
- Not in Schedules UI
- Chain breaks if the workflow is terminated or the chain activity hits a non-retryable error; transient failures are retried automatically, but unlike a Schedule there is no persistent server-side entity to restart the chain if the running workflow is killed first
- Each cycle has a unique workflow ID — harder to find without search attributes

---

## Approach 5 — Hybrid Calendar + Workflow-Side Day Check

**File:** `src/billing-5-daily-check.ts`
**Workflow:** `billingDailyCheckWorkflow`

A hybrid of approaches 1 and the daily-check idea. The key observation: only February's length varies year to year (28 days normally, 29 in a leap year). Every other month has a fixed last day, so approach 1's static per-month-group specs work perfectly for them.

For `billingDay <= 28`: a single spec fires on exactly that day every month — no checks needed.

For `billingDay 29–31`: non-February months get static per-month-group specs (like approach 1) that fire on exactly the right day with zero no-ops. February alone gets two specs (days 28 and 29); the schedule naturally skips day 29 in non-leap years because the date doesn't exist, and the workflow's day check handles the one remaining case (day 28 in a leap year when `billingDay >= 29`).

Result: at most 1 no-op — once every ~4 years (Feb 28 in a leap year when `billingDay >= 29`).

**Actions/cycle: 2 per real run + 2 per no-op**
| Event | Count (real run) | Count (no-op) |
|-------|-----------------|---------------|
| Schedule trigger | 2 | 2 |
| Workflow start | 1 | 1 |
| Activities (`generateInvoice` + `chargeCustomer`) | 2 | 0 |
| **Total** | **5** | **3** |

No-ops occur at most once every ~4 years (only on Feb 28 in a leap year when `billingDay >= 29`).

**Pros**
- Full Schedule UI: pause, backfill, describe, list
- Correct for any billing day, including end-of-month edge cases
- Simple: no circular dependencies, no chaining, no `continueAsNew`
- Near-zero no-ops: at most 1 per ~4 years

**Cons**
- Slightly more complex spec than approach 1 (February needs two entries)

---

## Summary

| | Schedule UI | End-of-month precision | Actions/cycle (real run) | Complexity |
|---|---|---|---|---|
| **1. Calendar schedule** | Yes | Approximate (Feb imprecise in leap years) | **5** | Low |
| **2. Self-reschedule** | Yes | Exact | **6** | Medium |
| **3. `continueAsNew` + sleep** | No | Exact | **4** | Medium |
| **4. Chain + `startDelay`** | No | Exact | **4** | Medium |
| **5. Hybrid calendar + day check** | Yes | Exact | **5** (+1 no-op per ~4 years) | Low |

Approach 5 is the simplest Schedule-based option that handles all billing days correctly. It uses static per-month-group specs for every month except February, falling back to a runtime day check only for the one month whose length varies — at most one no-op every four years.

---

## Running the Examples

```sh
# Terminal 1 — start Temporal dev server
just server

# Terminal 2 — start the worker (from this directory)
pnpm run start

# Terminal 3 — run any approach
pnpm run billing.1-calendar          # create schedule; trigger manually to test
pnpm run billing.2-self-reschedule   # create schedule; trigger manually to test
pnpm run billing.3-continue-as-new   # starts loop workflow immediately
pnpm run billing.4-chain-start-delay # starts first cycle; chains next with startDelay
pnpm run billing.5-daily-check       # create schedule; trigger manually to test
```

To trigger a schedule immediately for testing (approaches 1, 2 & 5):
```sh
temporal schedule trigger --schedule-id billing-calendar-cust-001
temporal schedule trigger --schedule-id billing-self-reschedule-cust-001
temporal schedule trigger --schedule-id billing-daily-check-cust-001
```

To inspect workflow state (approaches 3 & 4):
```sh
temporal workflow describe --workflow-id billing-loop-cust-001
temporal workflow list --query 'WorkflowId like "billing-chain-cust-001%"'
```
