package main

import (
	"log"

	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/contrib/envconfig"
	"go.temporal.io/sdk/worker"

	app "signal-queue"
)

func main() {
	c, err := client.Dial(envconfig.MustLoadDefaultClientOptions())
	if err != nil {
		log.Fatalln("Unable to create client", err)
	}
	defer c.Close()

	w := worker.New(c, app.TaskQueue, worker.Options{})
	w.RegisterWorkflow(app.LandingZoneDeploymentWorkflow)
	w.RegisterWorkflow(app.DeployChangesWorkflow)

	log.Printf("Starting worker on task queue %q...\n", app.TaskQueue)
	err = w.Run(worker.InterruptCh())
	if err != nil {
		log.Fatalln("Unable to start worker", err)
	}
}
