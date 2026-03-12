/**
 * Shared connection helpers for both the client and worker.
 *
 * Configuration is read from environment variables (or a TOML config file via
 * TEMPORAL_CONFIG_FILE).  The same variables work for local dev and Temporal
 * Cloud:
 *
 *   Local dev (defaults):
 *     TEMPORAL_ADDRESS=localhost:7233   (default)
 *     TEMPORAL_NAMESPACE=default        (default)
 *
 *   Temporal Cloud (mTLS):
 *     TEMPORAL_ADDRESS=<namespace>.tmprl.cloud:7233
 *     TEMPORAL_NAMESPACE=<namespace>.<accountId>
 *     TEMPORAL_TLS_CERT=/path/to/client.pem
 *     TEMPORAL_TLS_KEY=/path/to/client.key
 *
 *   Temporal Cloud (API key):
 *     TEMPORAL_ADDRESS=<namespace>.tmprl.cloud:7233
 *     TEMPORAL_NAMESPACE=<namespace>.<accountId>
 *     TEMPORAL_API_KEY=<your-api-key>
 *
 *   Profile (TOML config file):
 *     TEMPORAL_CONFIG_FILE=~/.config/temporalio/temporal.toml
 *     TEMPORAL_PROFILE=my-profile          (optional, defaults to "default")
 */

import { Connection } from '@temporalio/client';
import { loadClientConnectConfig } from '@temporalio/envconfig';
import { NativeConnection } from '@temporalio/worker';

export interface ConnectionBundle {
  /** Namespace resolved from config (falls back to 'default'). */
  namespace: string;
  /** Ready-to-use client Connection. */
  connection: Connection;
}

/**
 * Build a {@link Connection} (for use in client code) from the current
 * environment / config file.
 */
export async function connectClient(profile?: string): Promise<ConnectionBundle> {
  const config = loadClientConnectConfig({ profile });
  const connection = await Connection.connect(config.connectionOptions);
  return { connection, namespace: config.namespace ?? 'default' };
}

/**
 * Build a {@link NativeConnection} (for use in worker code) from the current
 * environment / config file.
 *
 * The caller is responsible for calling `connection.close()` when done.
 */
export async function connectWorker(profile?: string): Promise<{ connection: NativeConnection; namespace: string }> {
  const config = loadClientConnectConfig({ profile });
  const connection = await NativeConnection.connect(config.connectionOptions);
  return { connection, namespace: config.namespace ?? 'default' };
}
