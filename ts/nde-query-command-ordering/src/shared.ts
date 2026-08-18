import type { InjectedSinks, WorkerOptions } from '@temporalio/worker';
import type { TraceSinks } from './tracer';

// 127.0.0.1 rather than localhost on purpose: if anything else is bound to :7233 over IPv6 (a
// Temporal in Docker, say), `localhost` can resolve to a different server for the SDK than for the
// `temporal` CLI, and you get confusing "workflow not found" errors.
export const ADDRESS = process.env.TEMPORAL_ADDRESS ?? '127.0.0.1:7233';
export const NAMESPACE = process.env.TEMPORAL_NAMESPACE ?? 'default';
export const TASK_QUEUE = 'nde-query-command-ordering';

/**
 * TEST INSTRUMENTATION. Wires `tracer.ts` into a Worker (live or replay).
 *
 * `callDuringReplay: true` is required -- `processSinkCalls` suppresses non-replay sinks on replay
 * workers, and the replay pass is half the evidence.
 */
export function tracing(prefix: string): Pick<WorkerOptions, 'sinks' | 'interceptors'> {
  const sinks: InjectedSinks<TraceSinks> = {
    trace: {
      log: {
        fn: (_info, line) => console.log(`[${prefix}] ${line}`),
        callDuringReplay: true,
      },
    },
  };
  return { sinks, interceptors: { workflowModules: [require.resolve('./tracer')] } };
}
