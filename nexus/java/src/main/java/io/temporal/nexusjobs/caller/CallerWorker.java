package io.temporal.nexusjobs.caller;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.envconfig.ClientConfigProfile;
import io.temporal.nexusjobs.Config;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;
import java.io.IOException;

/**
 * Caller worker, in its own namespace — the whole point of a Nexus call is that it crosses a
 * namespace boundary.
 *
 * <p>JobCallerWorkflowImpl names the endpoint on its stub. To keep the endpoint out of workflow code
 * instead, drop the setEndpoint call there and register like this:
 *
 * <pre>{@code
 * worker.registerWorkflowImplementationTypes(
 *     WorkflowImplementationOptions.newBuilder()
 *         .setNexusServiceOptions(
 *             Collections.singletonMap(
 *                 "JobService",
 *                 NexusServiceOptions.newBuilder().setEndpoint(Config.NEXUS_ENDPOINT).build()))
 *         .build(),
 *     JobCallerWorkflowImpl.class);
 * }</pre>
 */
public class CallerWorker {

  public static void main(String[] args) throws IOException {
    // The caller profile carries its own address, namespace, and API key — which may belong to a
    // different Temporal Cloud account than the handler's.
    ClientConfigProfile profile = Config.loadProfile(Config.Role.CALLER);
    String namespace = Config.namespaceFor(Config.Role.CALLER, profile);

    WorkflowServiceStubs service =
        WorkflowServiceStubs.newServiceStubs(profile.toWorkflowServiceStubsOptions());
    WorkflowClient client =
        WorkflowClient.newInstance(
            service, WorkflowClientOptions.newBuilder().setNamespace(namespace).build());

    WorkerFactory factory = WorkerFactory.newInstance(client);
    Worker worker = factory.newWorker(Config.CALLER_TASK_QUEUE);
    worker.registerWorkflowImplementationTypes(JobCallerWorkflowImpl.class);

    factory.start();
    System.out.printf(
        "Caller worker polling namespace=%s taskQueue=%s%n", namespace, Config.CALLER_TASK_QUEUE);
  }
}
