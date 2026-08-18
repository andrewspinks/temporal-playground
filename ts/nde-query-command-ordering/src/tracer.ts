/**
 * TEST INSTRUMENTATION -- NOT part of the reconstructed customer workflow.
 *
 * Nothing in the production histories implies the customer uses interceptors; their workflow tasks
 * record `langUsedFlags: [2]` only, which means none of the interceptor-related SDK flags were ever
 * queried.
 *
 * This exists purely so we can read the command order out of every activation instead of inferring
 * it from event JSON afterwards. It is registered separately, via
 * `interceptors: { workflowModules: [require.resolve('./tracer')] }`, so it never mixes into
 * `workflows.ts`.
 *
 * `WorkflowInternalsInterceptor.concludeActivation` hands us the literal command list. Both
 * `interceptors` and `sinks` survive into `ReplayWorkerOptions`, so this same hook instruments the
 * live pass and the replay pass -- which is the point: two strings, same code, same history.
 */
import { proxySinks, workflowInfo, type Sinks, type WorkflowInterceptors } from '@temporalio/workflow';

export interface TraceSinks extends Sinks {
  trace: { log(line: string): void };
}

const { trace } = proxySinks<TraceSinks>();

/** Short names so a whole Workflow Task's commands read as one string, e.g. `ASAAAAA`. */
const SHORT: Record<string, string> = {
  scheduleActivity: 'A',
  signalExternalWorkflowExecution: 'S',
};

export const interceptors = (): WorkflowInterceptors => ({
  internals: [
    {
      activate(input, next) {
        const counts = new Map<string, number>();
        for (const job of input.activation.jobs ?? []) {
          // `variant` is the protobuf oneof getter; it exists on the concrete class, not on the
          // `I...` interface the types claim we have.
          const v = (job as { variant?: string }).variant ?? 'unknown';
          counts.set(v, (counts.get(v) ?? 0) + 1);
        }
        const jobs = [...counts].map(([v, n]) => (n > 1 ? `${v} x${n}` : v)).join(', ');
        trace.log(`activate replaying=${workflowInfo().unsafe.isReplaying} jobs=[${jobs}]`);
        return next(input);
      },

      concludeActivation(input, next) {
        const cmds = input.commands.map((c) => {
          const k = Object.keys(c)[0];
          return SHORT[k] ?? `<${k}>`;
        });
        trace.log(`  commands=${cmds.join('') || '(none)'}`);
        return next(input);
      },
    },
  ],
  inbound: [],
  outbound: [],
});
