"""Workflow-ID construction for the worker-deployment / WCI system workflows.

These IDs are rebuilt inline (mirroring wci/client/id.go and the server's
worker_versioning constants) rather than imported, since the tool runs outside
the Go module.
"""

DELIM = ":"
DEPLOYMENT_PREFIX = "temporal-sys-worker-deployment"
VERSION_PREFIX = "temporal-sys-worker-deployment-version"
WCI_PREFIX = "temporal-sys-worker-controller-instance"


def deployment_wfid(deployment: str) -> str:
    return f"{DEPLOYMENT_PREFIX}{DELIM}{deployment}"


def version_wfid(deployment: str, build_id: str) -> str:
    return f"{VERSION_PREFIX}{DELIM}{deployment}{DELIM}{build_id}"


def wci_wfid(deployment: str, build_id: str) -> str:
    return f"{WCI_PREFIX}{DELIM}{deployment}{DELIM}{build_id}"
