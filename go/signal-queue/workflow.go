package signalqueue

import (
	"fmt"
	"time"

	"go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/workflow"
)

const TaskQueue = "signal-queue"

// DeploymentRequest is the signal payload for submitting a request.
type DeploymentRequest struct {
	RequestID        string `json:"request_id"`
	DeploymentModule string `json:"deploymentmodule"`
}

// LandingZoneDeploymentWorkflow processes requests from a signal-driven queue.
// Requests of the same DeploymentModule are processed sequentially; different modules run in parallel.
func LandingZoneDeploymentWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("LandingZoneDeploymentWorkflow started")

	channels := map[string]workflow.Channel{}
	signalCh := workflow.GetSignalChannel(ctx, "submit_deployment_request")
	pending := 0

	dispatch := func(req DeploymentRequest) {
		if _, ok := channels[req.DeploymentModule]; !ok {
			ch := workflow.NewChannel(ctx)
			channels[req.DeploymentModule] = ch
			module := req.DeploymentModule
			workflow.Go(ctx, func(gCtx workflow.Context) {
				for {
					var r DeploymentRequest
					ch.Receive(gCtx, &r)

					logger.Info("Processing request", "deploymentModule", module, "requestID", r.RequestID)
					childCtx := workflow.WithChildOptions(gCtx, workflow.ChildWorkflowOptions{
						WorkflowID:        fmt.Sprintf("%s-%s-%s", workflow.GetInfo(gCtx).WorkflowExecution.ID, module, r.RequestID),
						ParentClosePolicy: enums.PARENT_CLOSE_POLICY_REQUEST_CANCEL,
					})

					var result string
					if err := workflow.ExecuteChildWorkflow(childCtx, DeployChangesWorkflow, r).Get(gCtx, &result); err != nil {
						logger.Error("Child workflow failed", "deploymentModule", module, "requestID", r.RequestID, "error", err)
					} else {
						logger.Info("Processed request", "deploymentModule", module, "requestID", r.RequestID, "result", result)
					}
					pending--
				}
			})
		}

		pending++
		ch := channels[req.DeploymentModule]
		r := req
		workflow.Go(ctx, func(gCtx workflow.Context) {
			ch.Send(gCtx, r)
		})
	}

	// Goroutine continuously drains signals
	workflow.Go(ctx, func(gCtx workflow.Context) {
		for {
			var req DeploymentRequest
			signalCh.Receive(gCtx, &req)
			dispatch(req)
		}
	})

	// Main loop: idle detection
	// Wait until all pending work completes, then wait for new work to arrive.
	// If no new work arrives within the timeout, shut down.
	for {
		workflow.Await(ctx, func() bool { return pending == 0 })
		newWork, _ := workflow.AwaitWithTimeout(ctx, 1*time.Minute, func() bool {
			return pending > 0
		})
		if !newWork {
			break
		}
	}

	if pending > 0 {
		workflow.Await(ctx, func() bool { return pending == 0 })
	}

	logger.Info("All work complete, workflow finishing")
	return nil
}

// DeployChangesWorkflow simulates processing a single request for a DeploymentModule.
func DeployChangesWorkflow(ctx workflow.Context, deployment DeploymentRequest) (string, error) {
	logger := workflow.GetLogger(ctx)
	logger.Info("DeployChangesWorkflow started", "deploymentModule", deployment.DeploymentModule, "requestID", deployment.RequestID)

	if err := workflow.Sleep(ctx, 15*time.Second); err != nil {
		return "", err
	}

	return deployment.RequestID, nil
}
