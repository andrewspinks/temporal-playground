package main

import (
	"context"
	"log"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/contrib/envconfig"

	app "payment-update"
)

func main() {
	// The client is a heavyweight object that should be created once per process.
	c, err := client.Dial(envconfig.MustLoadDefaultClientOptions())
	if err != nil {
		log.Fatalln("Unable to create client", err)
	}
	defer c.Close()

	ctx := context.Background()

	we, err := c.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:        app.WorkflowID,
		TaskQueue: app.TaskQueue,
	}, app.PaymentWorkflow)
	if err != nil {
		log.Fatalln("Unable to execute workflow", err)
	}
	log.Println("Started workflow", "WorkflowID", we.GetID(), "RunID", we.GetRunID())

	// Two valid payments. Each Update blocks until its Activity has run.
	submit(ctx, c, "update-1", app.PaymentRequest{PaymentAmount: 42.50, Currency: "USD"})
	submit(ctx, c, "update-2", app.PaymentRequest{PaymentAmount: 19.99, Currency: "EUR"})

	// An invalid payload: the validator rejects it, so no Activity runs and
	// nothing is written to history.
	submit(ctx, c, "update-3", app.PaymentRequest{PaymentAmount: 0, Currency: "USD"})

	if err := c.SignalWorkflow(ctx, we.GetID(), we.GetRunID(), app.ExitSignal, nil); err != nil {
		log.Fatalln("Unable to signal workflow", err)
	}

	var summary app.Summary
	if err := we.Get(ctx, &summary); err != nil {
		log.Fatalln("Unable to get workflow result", err)
	}
	log.Printf("Workflow result: %d payment(s), totals %v", summary.Count, summary.Totals)
}

// submit sends one Update and waits for the handler to finish.
func submit(ctx context.Context, c client.Client, updateID string, req app.PaymentRequest) {
	handle, err := c.UpdateWorkflow(ctx, client.UpdateWorkflowOptions{
		UpdateID:     updateID,
		WorkflowID:   app.WorkflowID,
		UpdateName:   app.SubmitPaymentUpdate,
		Args:         []interface{}{req},
		WaitForStage: client.WorkflowUpdateStageCompleted,
	})
	if err != nil {
		// Reached only for problems sending the Update, not for handler or
		// validator errors -- those surface from handle.Get below.
		log.Fatalln("Unable to send update", err)
	}

	var result app.PaymentResult
	if err := handle.Get(ctx, &result); err != nil {
		log.Printf("Update %s failed: %v", updateID, err)
		return
	}
	log.Printf("Update %s charged %s, receipt %s", updateID, result.Charged, result.ReceiptID)
}
