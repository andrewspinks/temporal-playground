package signalqueue

import (
	"time"

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

	signalCh := workflow.GetSignalChannel(ctx, "submit_deployment_request")
	dispatcher := NewModuleDispatcher(ctx)

	// Goroutine continuously drains signals
	workflow.Go(ctx, func(gCtx workflow.Context) {
		for {
			var req DeploymentRequest
			signalCh.Receive(gCtx, &req)
			dispatcher.Dispatch(req)
		}
	})

	// Idle detection: wait until all pending work completes, then wait for new work.
	// If no new work arrives within the timeout, shut down.
	for {
		workflow.Await(ctx, func() bool { return dispatcher.AllComplete() })
		newWork, _ := workflow.AwaitWithTimeout(ctx, 1*time.Minute, func() bool {
			return dispatcher.HasWork()
		})
		if !newWork {
			break
		}
	}

	if dispatcher.HasWork() {
		workflow.Await(ctx, func() bool { return dispatcher.AllComplete() })
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
