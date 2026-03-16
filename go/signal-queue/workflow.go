package signalqueue

import (
	"fmt"
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
// Requests of the same type are processed sequentially; different types run in parallel.
// Uses a Selector on the signal channel to dispatch to per-type Channels.
// Runs indefinitely, using continue-as-new to bound history.
func LandingZoneDeploymentWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("LandingZoneDeploymentWorkflow started")

	channels := map[string]workflow.Channel{}
	signalCh := workflow.GetSignalChannel(ctx, "submit_deployment_request")

	for {
		selector := workflow.NewSelector(ctx)
		selector.AddReceive(signalCh, func(receiveChannel workflow.ReceiveChannel, more bool) {
			var req DeploymentRequest
			receiveChannel.Receive(ctx, &req)

			// Create a per deployment module channel and goroutine on first sight of a new type
			if _, ok := channels[req.DeploymentModule]; !ok {
				deploymentModule := req.DeploymentModule
				deploymentModuleChannel := workflow.NewChannel(ctx)
				channels[req.DeploymentModule] = deploymentModuleChannel
				workflow.Go(ctx, func(gCtx workflow.Context) {
					processDeploymentModule(gCtx, deploymentModule, deploymentModuleChannel)
				})
			}

			ch := channels[req.DeploymentModule]
			workflow.Go(ctx, func(gCtx workflow.Context) {
				ch.Send(gCtx, req.RequestID)
			})
		})
		selector.Select(ctx)

		// Guard against unbounded history growth
		if workflow.GetInfo(ctx).GetCurrentHistoryLength() > 10_000 {
			return workflow.NewContinueAsNewError(ctx, LandingZoneDeploymentWorkflow)
		}
	}
}

// processDeploymentModule sequentially processes requests for a single deployment module from the given channel.
func processDeploymentModule(ctx workflow.Context, deploymentModule string, ch workflow.ReceiveChannel) {
	logger := workflow.GetLogger(ctx)
	for {
		var requestID string
		ch.Receive(ctx, &requestID)

		logger.Info("Processing request", "deploymentModule", deploymentModule, "requestID", requestID)

		childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
			WorkflowID: fmt.Sprintf("%s-%s-%s", workflow.GetInfo(ctx).WorkflowExecution.ID, deploymentModule, requestID),
			TaskQueue:  TaskQueue,
		})

		var result string
		if err := workflow.ExecuteChildWorkflow(childCtx, DeployChangesWorkflow, DeploymentRequest{DeploymentModule: deploymentModule, RequestID: requestID}).Get(ctx, &result); err != nil {
			logger.Error("Child workflow failed", "deploymentModule", deploymentModule, "requestID", requestID, "error", err)
			return
		}
		logger.Info("Processed request", "deploymentModule", deploymentModule, "requestID", requestID, "result", result)
	}
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
