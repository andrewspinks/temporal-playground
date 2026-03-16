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

		// SignalWithStartWorkflow atomically starts the scheduler workflow (if not
		// already running) and sends the submit_request signal with the request.
		_, err := c.SignalWithStartWorkflow(
			r.Context(),
			req.LZ_ID,                   // workflow ID
			"submit_deployment_request", // signal name
			app.DeploymentRequest{ // signal arg
				RequestID:        req.RequestID,
				DeploymentModule: req.DeploymentModule,
			},
			client.StartWorkflowOptions{
				TaskQueue: app.TaskQueue,
			},
			app.LandingZoneDeploymentWorkflow, // workflow function
		)
		if err != nil {
			log.Printf("SignalWithStartWorkflow failed: %v", err)
			http.Error(w, "failed to submit request", http.StatusInternalServerError)
			return
		}

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
