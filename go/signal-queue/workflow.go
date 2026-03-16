package signalqueue

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/workflow"
)

const TaskQueue = "signal-queue"

// SubmitRequest is the signal payload for submitting a request.
type SubmitRequest struct {
	RequestID string `json:"request_id"`
	Type      string `json:"type"`
}

// RequestSchedulerWorkflow processes requests from a signal-driven queue.
// Requests of the same type are processed sequentially; different types run in parallel.
// Uses a Selector on the signal channel to dispatch to per-type Channels.
// Runs indefinitely, using continue-as-new to bound history.
func RequestSchedulerWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestSchedulerWorkflow started")

	channels := map[string]workflow.Channel{}
	signalCh := workflow.GetSignalChannel(ctx, "submit_request")

	for {
		selector := workflow.NewSelector(ctx)
		selector.AddReceive(signalCh, func(c workflow.ReceiveChannel, more bool) {
			var req SubmitRequest
			c.Receive(ctx, &req)

			// Create a per-type channel and goroutine on first sight of a new type
			if _, ok := channels[req.Type]; !ok {
				channels[req.Type] = workflow.NewChannel(ctx)
				ch := channels[req.Type]
				typ := req.Type
				workflow.Go(ctx, func(gCtx workflow.Context) {
					processType(gCtx, typ, ch)
				})
			}

			ch := channels[req.Type]
			workflow.Go(ctx, func(gCtx workflow.Context) {
				ch.Send(gCtx, req.RequestID)
			})
		})
		selector.Select(ctx)

		// Guard against unbounded history growth
		if workflow.GetInfo(ctx).GetCurrentHistoryLength() > 10_000 {
			return workflow.NewContinueAsNewError(ctx, RequestSchedulerWorkflow)
		}
	}
}

// processType sequentially processes requests for a single type from the given channel.
func processType(ctx workflow.Context, queueType string, ch workflow.ReceiveChannel) {
	logger := workflow.GetLogger(ctx)
	for {
		var requestID string
		ch.Receive(ctx, &requestID)

		logger.Info("Processing request", "type", queueType, "requestID", requestID)

		childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
			WorkflowID: fmt.Sprintf("%s-%s-%s", workflow.GetInfo(ctx).WorkflowExecution.ID, queueType, requestID),
			TaskQueue:  TaskQueue,
		})

		var result string
		if err := workflow.ExecuteChildWorkflow(childCtx, RequestWorkflow, requestID).Get(ctx, &result); err != nil {
			logger.Error("Child workflow failed", "type", queueType, "requestID", requestID, "error", err)
			return
		}
		logger.Info("Processed request", "type", queueType, "requestID", requestID, "result", result)
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
