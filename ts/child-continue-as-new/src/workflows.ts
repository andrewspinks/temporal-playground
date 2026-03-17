import { condition, defineSignal, executeChild, setHandler } from '@temporalio/workflow';

export const spawnChildSignal = defineSignal('spawnChild');

export async function parentWorkflow(): Promise<string> {
  let shouldSpawn = false;
  setHandler(spawnChildSignal, () => {
    shouldSpawn = true;
  });
  await condition(() => shouldSpawn);
  return await executeChild(childWorkflow, { args: ['Alice'], workflowId: 'child-Alice' });
}

export async function childWorkflow(name: string): Promise<string> {
  return `Hello ${name}`;
}
