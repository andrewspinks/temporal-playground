// @@@SNIPSTART typescript-hello-workflow
import { proxyActivities, sleep, setHandler, defineUpdate, condition } from '@temporalio/workflow';
// Only import the activity types
import type * as activities from './activities';

const { greet } = proxyActivities<typeof activities>({
  startToCloseTimeout: '3 minutes',
});

export const setValueUpdate = defineUpdate<string, [string]>('setValue');

export async function example(name: string): Promise<string> {
  let value: string | null = null;

  setHandler(setValueUpdate, async (newValue: string) => {
    await sleep(2500);
    value = `${value}, ${newValue}`;

    return '${newValue} after 250 ms';
  });

  const greeting = await greet(name);

  // await wf.condition(wf.allHandlersFinished);
  // await workflow.allHandlersComplete
  // await condition(() => value !== null);

  return `${greeting} (value: ${value})`;
  // return `(value: ${value})`;
}
