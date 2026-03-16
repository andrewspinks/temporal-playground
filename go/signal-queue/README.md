# Signal Queue

A Temporal workflow that uses signals to implement a request queue. An HTTP API accepts requests and routes them to a per-ID scheduler workflow using `SignalWithStartWorkflow`. Each scheduler processes requests sequentially as child workflows, and an "exit" signal drains the queue and completes the workflow.

## Commands

Start the worker:

```sh
go run ./worker
```

Start the API server (port 8090):

```sh
go run ./api
```

Submit a request:

```sh
curl -s -X POST http://localhost:8090/request \
  -H "Content-Type: application/json" \
  -d '{"lz_id": "lz-1", "request_id": "req-1"}' | jq .
```

Send exit signal to drain and complete a scheduler workflow:

```sh
temporal workflow signal --workflow-id lz-1 --name exit
```

Build and test:

```sh
go build ./...
go test ./...
go mod tidy
```
