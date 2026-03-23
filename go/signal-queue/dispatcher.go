package signalqueue

import (
	"fmt"

	"go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/workflow"
)

// ModuleDispatcher routes requests to per-module sequential queues.
// Requests for the same module are processed one at a time via child workflows;
// different modules run in parallel.
type ModuleDispatcher struct {
	ctx      workflow.Context
	channels map[string]workflow.Channel
	pending  int
}

func NewModuleDispatcher(ctx workflow.Context) *ModuleDispatcher {
	return &ModuleDispatcher{
		ctx:      ctx,
		channels: map[string]workflow.Channel{},
	}
}

func (d *ModuleDispatcher) Dispatch(req DeploymentRequest) {
	logger := workflow.GetLogger(d.ctx)

	if _, ok := d.channels[req.DeploymentModule]; !ok {
		ch := workflow.NewChannel(d.ctx)
		d.channels[req.DeploymentModule] = ch
		module := req.DeploymentModule
		workflow.Go(d.ctx, func(gCtx workflow.Context) {
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
				d.pending--
			}
		})
	}

	d.pending++
	ch := d.channels[req.DeploymentModule]
	r := req
	workflow.Go(d.ctx, func(gCtx workflow.Context) {
		ch.Send(gCtx, r)
	})
}

// AllComplete returns true when no child workflows are in-flight.
func (d *ModuleDispatcher) AllComplete() bool {
	return d.pending == 0
}

// HasWork returns true when at least one child workflow is in-flight.
func (d *ModuleDispatcher) HasWork() bool {
	return d.pending > 0
}
