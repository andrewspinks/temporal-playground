package io.temporal.samples.hello;

import io.temporal.activity.ActivityOptions;
import io.temporal.failure.ActivityFailure;
import io.temporal.failure.CanceledFailure;
import io.temporal.workflow.CancellationScope;
import io.temporal.workflow.Workflow;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CancellationWorkflowImpl implements CancellationWorkflow {

    private static final Logger log = LoggerFactory.getLogger(
        CancellationWorkflowImpl.class
    );

    private boolean cancelActivity = false;
    private String cancellationReason = null;

    private final LongRunningActivity activities = Workflow.newActivityStub(
        LongRunningActivity.class,
        ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofMinutes(10))
            .setHeartbeatTimeout(Duration.ofMinutes(3))
            .build()
    );

    @Override
    public String run() {
        CancellationScope cancelScope = Workflow.newDetachedCancellationScope(
            () -> handleWorkflowCancel("workflow-cancelled")
        );

        CancellationScope waitForHandlers =
            Workflow.newDetachedCancellationScope(() -> {
                log.info(
                    "[workflow] isEveryHandlerFinished - waiting for all handlers"
                );
                Workflow.await(Workflow::isEveryHandlerFinished);
                log.info("[workflow] isEveryHandlerFinished - completed");
            });

        try {
            log.info("[workflow] Starting activity");
            String result = activities.doWork();
            log.info("[workflow] Activity completed normally: {}", result);
            cancelActivity = true;
            return result;
        } catch (CanceledFailure e) {
            log.info(
                "[workflow] CanceledFailure caught — running cancellation handler"
            );
            cancelScope.run();
            return "cancellationReason";
        } catch (ActivityFailure e) {
            if (e.getCause() instanceof CanceledFailure) {
                log.info(
                    "[workflow] ActivityFailure caught — running cancellation handler"
                );
                cancelScope.run();
                return cancellationReason;
            }
            throw e;
        } finally {
            // This doesn't seem to make any difference. Works regardless.
            // Activity still running as the handler is finished, but the activity cleanup is not - i.e. its still stopping the thread executor.
            waitForHandlers.run();
        }
    }

    private void handleWorkflowCancel(String reason) {
        log.info("[workflow] handleWorkflowCancel: reason={}", reason);
        cancellationReason = reason;
        cancelActivity = true;
    }

    @Override
    public CancellationStatus checkForWorkflowCancellation() {
        log.info(
            "[workflow] checkForWorkflowCancellation update received — waiting for shouldComplete"
        );
        Workflow.await(() -> cancelActivity);
        log.info(
            "[workflow] checkForWorkflowCancellation resolving — cancellationReason='{}'",
            cancellationReason
        );
        return cancellationReason.isEmpty()
            ? CancellationStatus.notCancelled()
            : CancellationStatus.cancelled(cancellationReason);
    }

    @Override
    public void signalMockCancel() {
        handleWorkflowCancel("from signal");
    }
}
