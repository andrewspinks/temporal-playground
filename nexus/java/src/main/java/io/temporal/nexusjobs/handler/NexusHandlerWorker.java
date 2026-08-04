package io.temporal.nexusjobs.handler;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.envconfig.ClientConfigProfile;
import io.temporal.nexusjobs.Config;
import io.temporal.nexusjobs.activities.TodoActivitiesImpl;
import io.temporal.nexusjobs.todo.TodoApi;
import io.temporal.nexusjobs.todo.TodoApiClient;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;
import io.temporal.worker.WorkerOptions;
import java.io.IOException;

/**
 * The handler side: serves JobService, and hosts the workflow + activity behind its async operation.
 *
 * <p>One worker polls this task queue for all three task types — Nexus, workflow, and activity.
 *
 * <p>It runs behind its own endpoint on its own task queue, deliberately. Sharing a task queue with
 * the playground's Python Nexus handler does not work: Temporal hands a Nexus task to whichever
 * worker polls first and does <b>not</b> route by service name, so roughly half of all tasks reach a
 * worker that has never heard of the requested service. That yields a NOT_FOUND handler error, which
 * is non-retryable by default, so those operations fail permanently rather than being redelivered.
 * An endpoint maps to exactly one (namespace, task queue), so one endpoint serving two languages
 * would require a single worker registering both services. `just java-collision-demo` reproduces it.
 */
public class NexusHandlerWorker {

  public static void main(String[] args) throws IOException {
    ClientConfigProfile profile = Config.loadProfile(Config.Role.HANDLER);
    String namespace = Config.namespaceFor(Config.Role.HANDLER, profile);

    WorkflowServiceStubs service =
        WorkflowServiceStubs.newServiceStubs(profile.toWorkflowServiceStubsOptions());
    WorkflowClient client =
        WorkflowClient.newInstance(
            service, WorkflowClientOptions.newBuilder().setNamespace(namespace).build());

    // Shared by the sync operation and the activity, so both paths do identical work.
    TodoApi todoApi = new TodoApiClient();

    WorkerFactory factory = WorkerFactory.newInstance(client);
    Worker worker =
        factory.newWorker(
            Config.HANDLER_TASK_QUEUE,
            WorkerOptions.newBuilder().setMaxConcurrentNexusTaskPollers(1).build());
    worker.registerNexusServiceImplementation(new JobServiceImpl(todoApi));
    worker.registerWorkflowImplementationTypes(FetchTodoWorkflowImpl.class);
    worker.registerActivitiesImplementations(new TodoActivitiesImpl(todoApi));

    factory.start();
    System.out.printf(
        "Nexus handler worker polling namespace=%s taskQueue=%s (endpoint %s)%n",
        namespace, Config.HANDLER_TASK_QUEUE, Config.NEXUS_ENDPOINT);
  }
}
