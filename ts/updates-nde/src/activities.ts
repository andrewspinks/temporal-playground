// @@@SNIPSTART typescript-hello-activity
import { sleep, activityInfo } from '@temporalio/activity';

export async function greet(name: string): Promise<string> {
  const { attempt } = activityInfo();
  if (attempt < 2) {
    await sleep('30 seconds');
    throw 'Soft timeout after 30 sec';
  } else {
    await sleep('30 seconds');
  }
  return `Hello, ${name}! (attempt ${attempt})`;
}
// @@@SNIPEND
