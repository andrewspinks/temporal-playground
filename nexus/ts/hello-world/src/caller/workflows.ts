import * as wf from '@temporalio/workflow';
import { sayHelloService } from '../api';

const ENDPOINT = 'hello-nexus-basic-nexus-endpoint';

export async function syncCallerWorkflow(name: string): Promise<string> {
  const client = wf.createNexusServiceClient({ service: sayHelloService, endpoint: ENDPOINT });
  const result = await client.executeOperation('mySyncOperation', { name }, { scheduleToCloseTimeout: '10s' });
  return result.message;
}

export async function asyncCallerWorkflow(name: string): Promise<string> {
  const client = wf.createNexusServiceClient({ service: sayHelloService, endpoint: ENDPOINT });
  const result = await client.executeOperation('sayHello', { name }, { scheduleToCloseTimeout: '30s' });
  return result.message;
}
