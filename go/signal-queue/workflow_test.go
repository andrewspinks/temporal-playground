package signalqueue

import (
	"testing"

	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/suite"
	"go.temporal.io/sdk/testsuite"
)

type WorkflowTestSuite struct {
	suite.Suite
	testsuite.WorkflowTestSuite
}

func TestWorkflowSuite(t *testing.T) {
	suite.Run(t, new(WorkflowTestSuite))
}

func (s *WorkflowTestSuite) sendUpdate(env *testsuite.TestWorkflowEnvironment, req DeploymentRequest) {
	env.UpdateWorkflow("submit_deployment_request", req.RequestID, &testsuite.TestUpdateCallback{
		OnReject:   func(err error) { s.Fail("update should not be rejected", err) },
		OnAccept:   func() {},
		OnComplete: func(interface{}, error) {},
	}, req)
}

func (s *WorkflowTestSuite) TestSameTypeProcessedSequentially() {
	env := s.NewTestWorkflowEnvironment()
	env.RegisterWorkflow(DeployChangesWorkflow)

	var deploymentExecutionOrder []string
	env.OnWorkflow(DeployChangesWorkflow, mock.Anything, mock.Anything).
		Return("done", nil).
		Run(func(args mock.Arguments) {
			deploymentExecutionOrder = append(deploymentExecutionOrder, args.Get(1).(DeploymentRequest).RequestID)
		})

	env.RegisterDelayedCallback(func() {
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeA", RequestID: "r1"})
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeA", RequestID: "r2"})
	}, 0)

	env.ExecuteWorkflow(LandingZoneDeploymentWorkflow)

	s.True(env.IsWorkflowCompleted())
	s.Equal([]string{"r1", "r2"}, deploymentExecutionOrder)
}

func (s *WorkflowTestSuite) TestDifferentTypesProcessedInParallel() {
	env := s.NewTestWorkflowEnvironment()
	env.RegisterWorkflow(DeployChangesWorkflow)

	var executed []DeploymentRequest
	env.OnWorkflow(DeployChangesWorkflow, mock.Anything, mock.Anything).
		Return("done", nil).
		Run(func(args mock.Arguments) {
			executed = append(executed, args.Get(1).(DeploymentRequest))
		})

	env.RegisterDelayedCallback(func() {
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeA", RequestID: "r1"})
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeA", RequestID: "r2"})
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeB", RequestID: "r3"})
		s.sendUpdate(env, DeploymentRequest{DeploymentModule: "typeA", RequestID: "r4"})
	}, 0)

	env.ExecuteWorkflow(LandingZoneDeploymentWorkflow)

	s.True(env.IsWorkflowCompleted())
	s.Len(executed, 4)
	s.Equal([]string{"r1", "r2", "r4"}, requestIDsForModule(executed, "typeA"))
	s.Equal([]string{"r3"}, requestIDsForModule(executed, "typeB"))
}

func requestIDsForModule(executed []DeploymentRequest, module string) []string {
	var ids []string
	for _, req := range executed {
		if req.DeploymentModule == module {
			ids = append(ids, req.RequestID)
		}
	}
	return ids
}
