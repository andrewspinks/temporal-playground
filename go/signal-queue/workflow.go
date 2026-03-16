package signalqueue

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/workflow"
)

const TaskQueue = "signal-queue"

// RequestSchedulerWorkflow processes requests from a signal-driven queue.
// Requests arrive via the "submit_request" signal and are processed sequentially
// as child workflows. The "exit" signal drains remaining requests and completes.
func RequestSchedulerWorkflow(ctx workflow.Context) ([]string, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestSchedulerWorkflow started")

	var pendingRequests []string
	var shouldExit bool

	// Register signal handlers
	submitCh := workflow.GetSignalChannel(ctx, "submit_request")
	exitCh := workflow.GetSignalChannel(ctx, "exit")

	// Drain any buffered signals into pendingRequests
	drainSignals := func() {
		for {
			var requestID string
			ok := submitCh.ReceiveAsync(&requestID)
			if !ok {
				break
			}
			pendingRequests = append(pendingRequests, requestID)
		}
		// Also check for exit signal
		var v any
		if exitCh.ReceiveAsync(&v) {
			shouldExit = true
		}
	}

	var greetings []string
	for {
		// Wait until we have requests or an exit signal
		workflow.Go(ctx, func(gCtx workflow.Context) {
			// This goroutine exists just to receive signals while we wait
		})

		// Block until there's something to process or exit
		drainSignals()
		if len(pendingRequests) == 0 && !shouldExit {
			// Wait for a signal
			selector := workflow.NewSelector(ctx)
			selector.AddReceive(submitCh, func(c workflow.ReceiveChannel, more bool) {
				var requestID string
				c.Receive(ctx, &requestID)
				pendingRequests = append(pendingRequests, requestID)
			})
			selector.AddReceive(exitCh, func(c workflow.ReceiveChannel, more bool) {
				c.Receive(ctx, nil)
				shouldExit = true
			})
			selector.Select(ctx)
			// After waking, drain any additional buffered signals
			drainSignals()
		}

		// Process all pending requests
		for len(pendingRequests) > 0 {
			requestID := pendingRequests[0]
			pendingRequests = pendingRequests[1:]

			logger.Info("Processing request", "requestID", requestID)

			childID := fmt.Sprintf("%s-%s", workflow.GetInfo(ctx).WorkflowExecution.ID, requestID)
			cwo := workflow.ChildWorkflowOptions{
				WorkflowID: childID,
				TaskQueue:  TaskQueue,
			}
			childCtx := workflow.WithChildOptions(ctx, cwo)

			var result string
			err := workflow.ExecuteChildWorkflow(childCtx, RequestWorkflow, requestID).Get(ctx, &result)
			if err != nil {
				return greetings, fmt.Errorf("child workflow failed for %s: %w", requestID, err)
			}
			greetings = append(greetings, fmt.Sprintf("Hello, %s", result))

			// Drain signals that arrived while processing
			drainSignals()
		}

		if shouldExit {
			logger.Info("Exit signal received, workflow completing", "greetings", len(greetings))
			return greetings, nil
		}
	}
}

// RequestWorkflow simulates processing a single request.
func RequestWorkflow(ctx workflow.Context, requestID string) (string, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestWorkflow started", "requestID", requestID)

	err := workflow.Sleep(ctx, 30*time.Second)
	if err != nil {
		return "", err
	}

	return requestID, nil
}
