export async function processTurnSignal(name: string): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return `Hello, ${name}!`;
}

export async function processWork(name: string): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, 600));
  return `Hello, ${name}!`;
}
