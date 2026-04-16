import * as wf from '@temporalio/workflow';
import type * as activities from './activities';

const { processWork, processTurnSignal } = wf.proxyActivities<typeof activities>({
  startToCloseTimeout: '30 seconds',
});

export const turnSignal = wf.defineSignal<[string]>('turnSignal');
export const flushUpdate = wf.defineUpdate<string, []>('flushUpdate');

export async function waitForSignals(): Promise<string> {
  const pendingWork: string[] = [];
  let processingDone = true;
  // let updateDone = false;

  wf.setHandler(turnSignal, async (data: string) => {
    pendingWork.push(data);
  });

  wf.setHandler(flushUpdate, async () => {
    await wf.condition(() => processingDone);
    // updateDone = true;
    return 'flushed';
  });

  while (true) {
    await wf.condition(() => pendingWork.length > 0);
    const batch = pendingWork.splice(0);

    for (const item of batch) {
      processingDone = false;
      await processTurnSignal(`model-step-${item}`);
      processingDone = true;

      // await wf.condition(() => updateDone);

      await processWork(`tool-call-${item}`);
    }
  }
}
