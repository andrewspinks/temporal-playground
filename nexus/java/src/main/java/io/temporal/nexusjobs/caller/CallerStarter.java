package io.temporal.nexusjobs.caller;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.client.WorkflowOptions;
import io.temporal.envconfig.ClientConfigProfile;
import io.temporal.nexusjobs.Config;
import io.temporal.serviceclient.WorkflowServiceStubs;
import java.io.IOException;

/** Starts the caller workflow and prints both operations' results. */
public class CallerStarter {

  public static void main(String[] args) throws IOException {
    int todoId = args.length > 0 ? Integer.parseInt(args[0]) : 1;

    ClientConfigProfile profile = Config.loadProfile(Config.Role.CALLER);
    String namespace = Config.namespaceFor(Config.Role.CALLER, profile);

    WorkflowServiceStubs service =
        WorkflowServiceStubs.newServiceStubs(profile.toWorkflowServiceStubsOptions());
    WorkflowClient client =
        WorkflowClient.newInstance(
            service, WorkflowClientOptions.newBuilder().setNamespace(namespace).build());

    JobCallerWorkflow workflow =
        client.newWorkflowStub(
            JobCallerWorkflow.class,
            WorkflowOptions.newBuilder()
                .setTaskQueue(Config.CALLER_TASK_QUEUE)
                .setWorkflowId("job-caller-todo-" + todoId)
                .build());

    try {
      CallerResult result = workflow.fetchBothWays(todoId);
      System.out.println();
      System.out.println("  fetchTodoSync  (handled inline)      : " + result.getViaSyncOperation());
      System.out.println(
          "      took " + result.getSyncOpMillis() + "ms — capped at 10s by the Nexus handler deadline");
      System.out.println("  fetchTodoAsync (backed by workflow)  : " + result.getViaAsyncOperation());
      System.out.println("      took " + result.getAsyncOpMillis() + "ms — no 10s ceiling");
      System.out.println();
    } finally {
      service.shutdown();
    }
  }
}
