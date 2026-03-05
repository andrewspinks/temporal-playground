package io.temporal.samples.hello;

import io.temporal.activity.Activity;
import io.temporal.activity.ActivityExecutionContext;
import io.temporal.client.WorkflowClient;
import java.time.Instant;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LongRunningActivityImpl implements LongRunningActivity {

    private static final Logger log = LoggerFactory.getLogger(
        LongRunningActivityImpl.class
    );

    private final WorkflowClient workflowClient;

    public LongRunningActivityImpl(WorkflowClient workflowClient) {
        this.workflowClient = workflowClient;
    }

    @Override
    public String doWork() {
        ActivityExecutionContext ctx = Activity.getExecutionContext();
        String workflowId = ctx.getInfo().getWorkflowId();
        log.info("[activity] Started. workflowId={}", workflowId);

        ExecutorService executor = Executors.newCachedThreadPool();
        AtomicReference<CancellationStatus> cancelStatus =
            new AtomicReference<>();

        Future<String> syncFuture = executor.submit(() -> {
            for (int i = 0; i < 10; i++) {
                log.info("[activity] Work step {}/10", i + 1);
                ctx.heartbeat("step-" + i);
                sleep(30_000);
            }
            return "COMPLETED_NORMALLY";
        });

        CancellationWorkflow workflowStub = workflowClient.newWorkflowStub(
            CancellationWorkflow.class,
            workflowId
        );
        log.info(
            "[activity] Sending checkForWorkflowCancellation update — monitoring for cancellation..."
        );
        Instant updateSentAt = Instant.now();

        executor.submit(() -> {
            try {
                CancellationStatus status =
                    workflowStub.checkForWorkflowCancellation(); // BLOCKING RPC
                long elapsedMs =
                    Instant.now().toEpochMilli() - updateSentAt.toEpochMilli();
                log.info(
                    "[activity] checkForWorkflowCancellation returned after {}ms: {}",
                    elapsedMs,
                    status
                );
                cancelStatus.set(status);
                if (status.isCancelled()) {
                    log.info(
                        "[activity] Cancelling sync thread — reason: {}",
                        status.getReason()
                    );
                    syncFuture.cancel(true); // directly interrupt the sync thread
                }
            } catch (Exception e) {
                log.warn("[activity] checkForWorkflowCancellation threw", e);
            }
        });

        try {
            return syncFuture.get();
        } catch (CancellationException e) {
            CancellationStatus status = cancelStatus.get();
            long elapsedMs =
                Instant.now().toEpochMilli() - updateSentAt.toEpochMilli();
            String reason = status != null ? status.getReason() : "unknown";
            log.info(
                "[activity] Stopped via update after {}ms — reason: {}",
                elapsedMs,
                reason
            );
            return "STOPPED_VIA_UPDATE after " + elapsedMs + "ms: " + reason;
        } catch (ExecutionException e) {
            throw Activity.wrap(e.getCause());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw Activity.wrap(e);
        } finally {
            log.info("[activity] Activity executor shutting down");
            executor.shutdownNow();
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted", e);
        }
    }
}
