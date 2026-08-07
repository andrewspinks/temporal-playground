// Package app shows how a Workflow Update carries a payload into an Activity.
//
// A client sends the "submitPayment" Update with a PaymentRequest. A validator
// screens the payload before it is admitted to history, and the Update handler
// passes the accepted payload straight to the ChargePayment Activity. The
// Activity's result is returned to the Update caller.
package app

import (
	"context"
	"fmt"
	"time"

	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

const (
	// TaskQueue is shared by the worker and the starter.
	TaskQueue = "payment-update"

	// WorkflowID is fixed so the starter can send Updates without looking it up.
	WorkflowID = "payment-update-workflow"

	// SubmitPaymentUpdate is the Update name clients send to charge a payment.
	SubmitPaymentUpdate = "submitPayment"

	// ExitSignal tells the Workflow to stop accepting payments and complete.
	ExitSignal = "exit"

	// DeclinedErrorType marks a decline as non-retryable, so a rejected card
	// surfaces to the Update caller instead of being retried.
	DeclinedErrorType = "CardDeclined"
)

// PaymentRequest is the Update payload.
//
// PaymentAmount is a float64 to keep the example small. Real money is better
// modeled as integer minor units (cents) or a decimal type.
type PaymentRequest struct {
	PaymentAmount float64 `json:"paymentAmount"`
	Currency      string  `json:"currency"`
}

// PaymentResult is what the Activity produces and the Update returns.
type PaymentResult struct {
	ReceiptID string `json:"receiptId"`
	Charged   string `json:"charged"`
}

// Summary is the Workflow's return value.
type Summary struct {
	Count  int                `json:"count"`
	Totals map[string]float64 `json:"totals"`
}

// PaymentWorkflow accepts payments via Update until it receives the exit Signal.
func PaymentWorkflow(ctx workflow.Context) (Summary, error) {
	logger := workflow.GetLogger(ctx)
	summary := Summary{Totals: map[string]float64{}}

	err := workflow.SetUpdateHandler(
		ctx,
		SubmitPaymentUpdate,
		func(ctx workflow.Context, req PaymentRequest) (PaymentResult, error) {
			actCtx := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
				StartToCloseTimeout: 120 * time.Second,
				RetryPolicy: &temporal.RetryPolicy{
					MaximumAttempts:        3,
					NonRetryableErrorTypes: []string{DeclinedErrorType},
				},
			})

			// The Update payload is handed to the Activity unchanged.
			var result PaymentResult
			if err := workflow.ExecuteActivity(actCtx, ChargePayment, req).Get(actCtx, &result); err != nil {
				return PaymentResult{}, err
			}

			// Handlers may mutate Workflow state; validators may not.
			summary.Count++
			summary.Totals[req.Currency] += req.PaymentAmount

			logger.Info("Charged payment", "receiptID", result.ReceiptID, "currency", req.Currency)
			return result, nil
		},
	)
	if err != nil {
		return Summary{}, err
	}

	exit := false
	workflow.Go(ctx, func(ctx workflow.Context) {
		workflow.GetSignalChannel(ctx, ExitSignal).Receive(ctx, nil)
		exit = true
	})

	if err := workflow.Await(ctx, func() bool { return exit }); err != nil {
		return Summary{}, err
	}

	// An Update handler that is mid-Activity would be cut off if the Workflow
	// returned now, so wait for in-flight handlers to drain first.
	if err := workflow.Await(ctx, func() bool { return workflow.AllHandlersFinished(ctx) }); err != nil {
		return Summary{}, err
	}

	return summary, nil
}

// ChargePayment stands in for a call to a payment gateway.
func ChargePayment(ctx context.Context, req PaymentRequest) (PaymentResult, error) {
	info := activity.GetInfo(ctx)
	activity.GetLogger(ctx).Info("Charging payment",
		"paymentAmount", req.PaymentAmount, "currency", req.Currency)

	time.Sleep(20 * time.Second)

	activity.GetLogger(ctx).Info("Finished payment",
		"paymentAmount", req.PaymentAmount, "currency", req.Currency)

	return PaymentResult{
		ReceiptID: "rcpt-" + info.ActivityID,
		Charged:   fmt.Sprintf("%.2f %s", req.PaymentAmount, req.Currency),
	}, nil
}
