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
	LZID      string `json:"lz_id"`
	RequestID string `json:"request_id"`
}

type Response struct {
	RequestID string `json:"request_id"`
	Status    string `json:"status"`
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

		if req.LZID == "" || req.RequestID == "" {
			http.Error(w, "lz_id and request_id are required", http.StatusBadRequest)
			return
		}

		// SignalWithStartWorkflow atomically starts the scheduler workflow (if not
		// already running) and sends the submit_request signal with the request ID.
		_, err := c.SignalWithStartWorkflow(
			r.Context(),
			req.LZID,            // workflow ID
			"submit_request",    // signal name
			req.RequestID,       // signal arg
			client.StartWorkflowOptions{
				TaskQueue: app.TaskQueue,
			},
			app.RequestSchedulerWorkflow, // workflow function
		)
		if err != nil {
			log.Printf("SignalWithStartWorkflow failed: %v", err)
			http.Error(w, "failed to submit request", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Response{
			RequestID: req.RequestID,
			Status:    "received",
		})
	})

	addr := ":8090"
	log.Printf("API server listening on %s\n", addr)
	log.Fatal(http.ListenAndServe(addr, nil))
}
