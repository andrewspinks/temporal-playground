package signalqueue

import (
	"errors"
	"time"

	"go.temporal.io/sdk/workflow"
)

var ErrWorkflowClosing = errors.New("workflow is shutting down")

const TaskQueue = "signal-queue"

// DeploymentRequest is the payload for submitting a deployment request.
type DeploymentRequest struct {
	RequestID        string `json:"request_id"`
	DeploymentModule string `json:"deploymentmodule"`
}

// LandingZoneDeploymentWorkflow processes requests via an update handler.
// Requests of the same DeploymentModule are processed sequentially; different modules run in parallel.
func LandingZoneDeploymentWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("LandingZoneDeploymentWorkflow started")

	closing := false
	dispatcher := NewModuleDispatcher(ctx)

	workflow.SetUpdateHandlerWithOptions(ctx, "submit_deployment_request",
		func(ctx workflow.Context, req DeploymentRequest) error {
			dispatcher.Dispatch(req)
			return nil
		},
		workflow.UpdateHandlerOptions{
			Validator: func(ctx workflow.Context, req DeploymentRequest) error {
				if closing {
					return ErrWorkflowClosing
				}
				return nil
			},
		},
	)

	// Idle detection: wait until all pending work completes, then wait for new work.
	// If no new work arrives within the timeout, shut down.
	for {
		workflow.Await(ctx, func() bool { return dispatcher.AllComplete() })
		newWork, _ := workflow.AwaitWithTimeout(ctx, 1*time.Minute, func() bool {
			return dispatcher.HasWork()
		})
		if !newWork {
			closing = true
			break
		}
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
