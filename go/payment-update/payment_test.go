package app

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"
)

func TestUpdateTriggersActivity(t *testing.T) {
	var ts testsuite.WorkflowTestSuite
	env := ts.NewTestWorkflowEnvironment()
	env.RegisterActivity(ChargePayment)

	var result PaymentResult
	var completeErr error

	env.RegisterDelayedCallback(func() {
		env.UpdateWorkflow(SubmitPaymentUpdate, "update-1", &testsuite.TestUpdateCallback{
			OnReject: func(err error) { completeErr = err },
			OnComplete: func(success interface{}, err error) {
				completeErr = err
				if pr, ok := success.(PaymentResult); ok {
					result = pr
				}
			},
		}, PaymentRequest{PaymentAmount: 42.50, Currency: "USD"})
	}, time.Second)

	env.RegisterDelayedCallback(func() {
		env.SignalWorkflow(ExitSignal, nil)
	}, 2*time.Second)

	env.ExecuteWorkflow(PaymentWorkflow)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
	require.NoError(t, completeErr)
	require.Equal(t, "42.50 USD", result.Charged)
	require.NotEmpty(t, result.ReceiptID)

	var summary Summary
	require.NoError(t, env.GetWorkflowResult(&summary))
	require.Equal(t, 1, summary.Count)
	require.Equal(t, 42.50, summary.Totals["USD"])
}

func TestValidatorRejectsBadPayload(t *testing.T) {
	var ts testsuite.WorkflowTestSuite
	env := ts.NewTestWorkflowEnvironment()
	env.RegisterActivity(ChargePayment)

	var rejectErr error
	accepted := false

	env.RegisterDelayedCallback(func() {
		env.UpdateWorkflow(SubmitPaymentUpdate, "update-1", &testsuite.TestUpdateCallback{
			OnAccept: func() { accepted = true },
			OnReject: func(err error) { rejectErr = err },
		}, PaymentRequest{PaymentAmount: 0, Currency: "USD"})
	}, time.Second)

	env.RegisterDelayedCallback(func() {
		env.SignalWorkflow(ExitSignal, nil)
	}, 2*time.Second)

	env.ExecuteWorkflow(PaymentWorkflow)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
	require.False(t, accepted)
	require.ErrorContains(t, rejectErr, "paymentAmount must be positive")

	// A rejected Update never reaches the handler, so no payment is recorded.
	var summary Summary
	require.NoError(t, env.GetWorkflowResult(&summary))
	require.Equal(t, 0, summary.Count)
}

func TestDeclineIsNotRetried(t *testing.T) {
	var ts testsuite.WorkflowTestSuite
	env := ts.NewTestWorkflowEnvironment()
	env.RegisterActivity(ChargePayment)

	var completeErr error

	env.RegisterDelayedCallback(func() {
		env.UpdateWorkflow(SubmitPaymentUpdate, "update-1", &testsuite.TestUpdateCallback{
			OnReject:   func(err error) { completeErr = err },
			OnComplete: func(_ interface{}, err error) { completeErr = err },
		}, PaymentRequest{PaymentAmount: 25_000, Currency: "USD"})
	}, time.Second)

	env.RegisterDelayedCallback(func() {
		env.SignalWorkflow(ExitSignal, nil)
	}, 2*time.Second)

	env.ExecuteWorkflow(PaymentWorkflow)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
	require.ErrorContains(t, completeErr, "card declined")
}
