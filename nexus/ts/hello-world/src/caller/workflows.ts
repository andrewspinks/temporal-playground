import * as wf from '@temporalio/workflow';
import { NexusOperationFailure } from '@temporalio/common';
import { sayHelloService } from '../api';

const ENDPOINT = 'hello-nexus-basic-nexus-endpoint';

export const callNexusSignal = wf.defineSignal<[string]>('callNexus');
export const finishSignal = wf.defineSignal('finish');
export const getResultsQuery = wf.defineQuery<string[]>('getResults');

export async function syncCallerWorkflow(name: string): Promise<string> {
  const client = wf.createNexusServiceClient({ service: sayHelloService, endpoint: ENDPOINT });
  const result = await client.executeOperation('mySyncOperation', { name }, { scheduleToCloseTimeout: '10s' });
  return result.message;
}

// Long-running workflow that calls the async nexus operation each time it receives a callNexus signal.
// Useful for exploring what happens when the handler workflow (started by the nexus operation) is reset.
// Send 'finish' signal to complete the workflow and get results.
export async function asyncCallerWorkflow(): Promise<string[]> {
  const client = wf.createNexusServiceClient({ service: sayHelloService, endpoint: ENDPOINT });
  const pendingNames: string[] = [];
  const results: string[] = [];
  let finished = false;

  wf.setHandler(callNexusSignal, (name) => {
    pendingNames.push(name);
  });

  wf.setHandler(finishSignal, () => {
    finished = true;
  });

  wf.setHandler(getResultsQuery, () => results);

  while (!finished) {
    await wf.condition(() => pendingNames.length > 0 || finished);
    if (pendingNames.length > 0) {
      const name = pendingNames.shift()!;
      try {
        const result = await client.executeOperation('sayHello', { name }, { scheduleToCloseTimeout: '30s' });
        results.push(result.message);
        wf.log.info('Nexus call completed', { name, message: result.message });
      } catch (err: unknown) {
        if (err instanceof NexusOperationFailure) {
          // Non-retryable: arrives immediately after the handler workflow fails.
          // Retryable: arrives after scheduleToCloseTimeout is exceeded.
          const cause = err.cause instanceof Error ? err.cause.message : String(err.cause);
          const msg = `[FAILED] ${err.operation}: ${cause}`;
          wf.log.error('Nexus async operation failed', { name, operation: err.operation });
          results.push(msg);
        } else {
          throw err;
        }
      }
    }
  }

  return results;
}
