# Signal Queue

A Temporal workflow that uses signals to implement a request queue. An HTTP API accepts requests and routes them to a per-ID scheduler workflow using `SignalWithStartWorkflow`. Requests of the same `type` (e.g. "subnet", "security-group") are processed sequentially, while different types run in parallel. The scheduler runs indefinitely, using continue-as-new to bound history growth.

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
  -d '{"lz_id": "lz-1", "deploymentmodule": "subnet", "request_id": "req-1"}' | jq .
```

Build and test:

```sh
go build ./...
go test ./...
go mod tidy
```
