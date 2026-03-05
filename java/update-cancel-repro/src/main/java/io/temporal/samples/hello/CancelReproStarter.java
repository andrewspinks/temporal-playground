package io.temporal.samples.hello;

import static io.temporal.samples.hello.TemporalStarter.createClient;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowOptions;
import io.temporal.serviceclient.WorkflowServiceStubs;
import java.time.Instant;

/**
 * Starts a CancellationWorkflow, waits for the activity to attach its update, then cancels.
 */
public class CancelReproStarter {

    public static void main(String[] args) throws InterruptedException {
        WorkflowClient client = createClient();

        String workflowId = "update-cancel-repro-" + System.currentTimeMillis();

        CancellationWorkflow workflow = client.newWorkflowStub(
            CancellationWorkflow.class,
            WorkflowOptions.newBuilder()
                .setWorkflowId(workflowId)
                .setTaskQueue(CancelReproWorker.TASK_QUEUE)
                .build()
        );

        System.out.println("Starting workflow: " + workflowId);
        Instant t0 = Instant.now();

        // Start async so we can cancel while it's running
        WorkflowClient.start(workflow::run);

        Thread.sleep(20_000);

        System.out.println(
            "Requesting cancellation at T+" + elapsed(t0) + "ms"
        );
        client.newUntypedWorkflowStub(workflowId).cancel();
        System.out.println(
            "Cancel requested. Watching for workflow completion..."
        );

        // Poll until workflow completes
        io.temporal.client.WorkflowStub stub = client.newUntypedWorkflowStub(
            workflowId
        );
        String result;
        try {
            result = stub.getResult(String.class);
        } catch (Exception e) {
            result = "EXCEPTION: " + e.getMessage();
        }

        long totalMs = Instant.now().toEpochMilli() - t0.toEpochMilli();
        System.out.println(
            "======================================================="
        );
        System.out.println("Workflow completed at T+" + totalMs + "ms");
        System.out.println("Result: " + result);
        System.out.println();
        System.out.println("Interpretation:");
        if (result != null && result.startsWith("cancelled:")) {
            System.out.println(
                "  FAST CANCELLATION via update — update handler ran in the cancellation task."
            );
        } else if (
            result != null &&
            result.startsWith("activity-cancelled-via-heartbeat")
        ) {
            System.out.println(
                "  SLOW CANCELLATION via heartbeat — update handler was NOT scheduled"
            );
            System.out.println(
                "  in the cancellation task. This reproduces the Cloud bug."
            );
        } else {
            System.out.println(
                "  Other outcome — check workflow history for details."
            );
        }
        System.out.println(
            "======================================================="
        );

        //    service.shutdown();
    }

    private static long elapsed(Instant from) {
        return Instant.now().toEpochMilli() - from.toEpochMilli();
    }
}
