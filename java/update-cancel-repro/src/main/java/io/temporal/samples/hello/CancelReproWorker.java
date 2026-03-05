package io.temporal.samples.hello;

import io.temporal.client.WorkflowClient;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.worker.Worker;
import io.temporal.worker.WorkerFactory;

import static io.temporal.samples.hello.TemporalStarter.createClient;

/**
 * Starts the worker for the update-cancellation repro.
 *
 * <p>Run this first, then run {@link CancelReproStarter} in a separate terminal.
 */
public class CancelReproWorker {

  static final String TASK_QUEUE = "update-cancel-repro";

  public static void main(String[] args) {
    WorkflowClient client = createClient();

    WorkerFactory factory = WorkerFactory.newInstance(client);

    Worker worker = factory.newWorker(TASK_QUEUE);

    // Register workflow implementation
    worker.registerWorkflowImplementationTypes(CancellationWorkflowImpl.class);

    // Register activity implementation — inject the WorkflowClient so the activity
    // can call checkCancellation() back on the workflow.
    worker.registerActivitiesImplementations(new LongRunningActivityImpl(client));

    factory.start();
    System.out.println("Worker started on task queue: " + TASK_QUEUE);
    System.out.println("Now run CancelReproStarter in another terminal.");
  }
}
