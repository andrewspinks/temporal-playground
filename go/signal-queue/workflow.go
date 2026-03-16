package signalqueue

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/workflow"
)

const TaskQueue = "signal-queue"

// RequestSchedulerWorkflow processes requests from a signal-driven queue.
// Requests arrive via the "submit_request" signal and are processed sequentially
// as child workflows. Runs indefinitely, using continue-as-new to bound history.
func RequestSchedulerWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestSchedulerWorkflow started")

	var pendingRequests []string

	// Goroutine continuously receives signals into the queue
	workflow.Go(ctx, func(gCtx workflow.Context) {
		submitSignalChannel := workflow.GetSignalChannel(gCtx, "submit_request")
		for {
			var requestID string
			submitSignalChannel.Receive(gCtx, &requestID)
			pendingRequests = append(pendingRequests, requestID)
		}
	})

	for {
		// Wait until queue is non-empty
		workflow.Await(ctx, func() bool { return len(pendingRequests) > 0 })

		// Drain and process queue
		for len(pendingRequests) > 0 {
			requestID := pendingRequests[0]
			pendingRequests = pendingRequests[1:]

			logger.Info("Processing request", "requestID", requestID)

			childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
				WorkflowID: fmt.Sprintf("%s-%s", workflow.GetInfo(ctx).WorkflowExecution.ID, requestID),
				TaskQueue:  TaskQueue,
			})

			var result string
			if err := workflow.ExecuteChildWorkflow(childCtx, RequestWorkflow, requestID).Get(ctx, &result); err != nil {
				return fmt.Errorf("child workflow failed for %s: %w", requestID, err)
			}
			logger.Info("Processed request", "requestID", requestID, "result", result)
		}

		// Guard against unbounded history growth
		if workflow.GetInfo(ctx).GetCurrentHistoryLength() > 10_000 {
			return workflow.NewContinueAsNewError(ctx, RequestSchedulerWorkflow)
		}
	}
}

// RequestWorkflow simulates processing a single request.
func RequestWorkflow(ctx workflow.Context, requestID string) (string, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestWorkflow started", "requestID", requestID)

	if err := workflow.Sleep(ctx, 15*time.Second); err != nil {
		return "", err
	}

	return requestID, nil
}
