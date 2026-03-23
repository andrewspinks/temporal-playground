package main

import (
	"encoding/json"
	"log"
	"net/http"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/contrib/envconfig"

	app "signal-queue"
)

type Request struct {
	LZ_ID            string `json:"lz_id"`
	RequestID        string `json:"request_id"`
	DeploymentModule string `json:"deploymentmodule"`
}

type Response struct {
	RequestID        string `json:"request_id"`
	DeploymentModule string `json:"deploymentmodule"`
	Status           string `json:"status"`
}

func main() {
	c, err := client.Dial(envconfig.MustLoadDefaultClientOptions())
	if err != nil {
		log.Fatalln("Unable to create Temporal client", err)
	}
	defer c.Close()

	http.HandleFunc("POST /request", func(w http.ResponseWriter, r *http.Request) {
		var req Request
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "invalid request body", http.StatusBadRequest)
			return
		}

		if req.LZ_ID == "" || req.RequestID == "" || req.DeploymentModule == "" {
			http.Error(w, "lz_id, request_id, and type are required", http.StatusBadRequest)
			return
		}

		deploymentReq := app.DeploymentRequest{
			RequestID:        req.RequestID,
			DeploymentModule: req.DeploymentModule,
		}

		// Start the workflow if not already running (idempotent via workflow ID).
		_, _ = c.ExecuteWorkflow(
			r.Context(),
			client.StartWorkflowOptions{
				ID:        req.LZ_ID,
				TaskQueue: app.TaskQueue,
			},
			app.LandingZoneDeploymentWorkflow,
		)

		// Send the deployment request via update handler.
		// If the workflow is shutting down, the update is rejected.
		updateHandle, err := c.UpdateWorkflow(
			r.Context(),
			client.UpdateWorkflowOptions{
				WorkflowID:   req.LZ_ID,
				UpdateName:   "submit_deployment_request",
				Args:         []interface{}{deploymentReq},
				WaitForStage: client.WorkflowUpdateStageAccepted,
			},
		)
		if err != nil {
			log.Printf("UpdateWorkflow failed: %v", err)
			http.Error(w, "failed to submit request: "+err.Error(), http.StatusConflict)
			return
		}
		_ = updateHandle

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Response{
			RequestID:        req.RequestID,
			DeploymentModule: req.DeploymentModule,
			Status:           "received",
		})
	})

	addr := ":8091"
	log.Printf("API server listening on %s\n", addr)
	log.Fatal(http.ListenAndServe(addr, nil))
}
