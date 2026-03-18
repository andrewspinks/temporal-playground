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
// Requests of the same DeploymentModule are processed sequentially; different modules run in parallel.
func LandingZoneDeploymentWorkflow(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("LandingZoneDeploymentWorkflow started")

	channels := map[string]workflow.Channel{}
	signalCh := workflow.GetSignalChannel(ctx, "submit_deployment_request")

	dispatch := func(req DeploymentRequest) {
		// Spin up a per-module channel on first sight of a new DeploymentModule
		if _, ok := channels[req.DeploymentModule]; !ok {
			ch := workflow.NewChannel(ctx)
			channels[req.DeploymentModule] = ch
			module := req.DeploymentModule
			workflow.Go(ctx, func(gCtx workflow.Context) {
				processDeploymentModule(gCtx, module, ch)
			})
		}

		ch := channels[req.DeploymentModule]
		r := req
		workflow.Go(ctx, func(gCtx workflow.Context) {
			ch.Send(gCtx, r)
		})
	}

	for {
		var req DeploymentRequest
		signalCh.Receive(ctx, &req)
		// for sliding expiry.
		// ok, _ := signalCh.ReceiveWithTimeout(ctx, 1*time.Minute, &req)
		// if !ok {
		// 	   logger.Info("No new requests for 5 minutes, exiting")
		//     return nil
		// }
		dispatch(req)
	}
}

// processDeploymentModule sequentially processes requests for a single deployment module from the given channel.
func processDeploymentModule(ctx workflow.Context, module string, ch workflow.ReceiveChannel) {
	logger := workflow.GetLogger(ctx)
	for {
		var req DeploymentRequest
		ch.Receive(ctx, &req)

		logger.Info("Processing request", "deploymentModule", module, "requestID", req.RequestID)

		childCtx := workflow.WithChildOptions(ctx, workflow.ChildWorkflowOptions{
			WorkflowID: fmt.Sprintf("%s-%s-%s", workflow.GetInfo(ctx).WorkflowExecution.ID, module, req.RequestID),
		})

		var result string
		if err := workflow.ExecuteChildWorkflow(childCtx, DeployChangesWorkflow, req).Get(ctx, &result); err != nil {
			logger.Error("Child workflow failed", "deploymentModule", module, "requestID", req.RequestID, "error", err)
			continue
		}
		logger.Info("Processed request", "deploymentModule", module, "requestID", req.RequestID, "result", result)
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
