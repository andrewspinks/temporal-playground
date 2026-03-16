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
// Runs indefinitely, using continue-as-new to bound history.
func RequestSchedulerWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("RequestSchedulerWorkflow started")

	// Per-type queues; each type gets a long-lived goroutine
	queues := map[string][]string{}
	started := map[string]bool{}

	// Goroutine continuously receives signals and routes to per-type queues
	workflow.Go(ctx, func(gCtx workflow.Context) {
		ch := workflow.GetSignalChannel(gCtx, "submit_request")
		for {
			var req SubmitRequest
			ch.Receive(gCtx, &req)
			queues[req.Type] = append(queues[req.Type], req.RequestID)
		}
	})

	for {
		// Wait until a new type appears that doesn't have a goroutine yet
		workflow.Await(ctx, func() bool {
			for typ := range queues {
				if !started[typ] {
					return true
				}
			}
			return false
		})

		// Spawn a long-lived goroutine for each new type
		for typ := range queues {
			if started[typ] {
				continue
			}
			started[typ] = true
			// typ := typ // capture loop var
			workflow.Go(ctx, func(gCtx workflow.Context) {
				for {
					// Wait until this type's queue has work
					workflow.Await(gCtx, func() bool { return len(queues[typ]) > 0 })

					for len(queues[typ]) > 0 {
						requestID := queues[typ][0]
						queues[typ] = queues[typ][1:]

						logger.Info("Processing request", "type", typ, "requestID", requestID)

						childCtx := workflow.WithChildOptions(gCtx, workflow.ChildWorkflowOptions{
							WorkflowID: fmt.Sprintf("%s-%s-%s", workflow.GetInfo(gCtx).WorkflowExecution.ID, typ, requestID),
							TaskQueue:  TaskQueue,
						})

						var result string
						if err := workflow.ExecuteChildWorkflow(childCtx, RequestWorkflow, requestID).Get(gCtx, &result); err != nil {
							logger.Error("Child workflow failed", "type", typ, "requestID", requestID, "error", err)
							return
						}
						logger.Info("Processed request", "type", typ, "requestID", requestID, "result", result)
					}
				}
			})
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
