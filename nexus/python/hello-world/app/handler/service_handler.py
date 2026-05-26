"""
This file demonstrates how to implement a Nexus service.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import nexusrpc
from temporalio import nexus
from temporalio.common import RetryPolicy

from app.handler.workflows import SayHelloWorkflow
from app.service import MyInput, SayHelloService, MyOutput


@nexusrpc.handler.service_handler(service=SayHelloService)
class SayHelloServiceHandler:
    # You can create an __init__ method accepting what is needed by your operation
    # handlers to handle requests. You typically instantiate your service handler class
    # when starting your worker. See hello_nexus/basic/handler/worker.py.

    # This is a nexus operation that is backed by a Temporal workflow. The start method
    # starts a workflow, and returns a nexus operation token. Meanwhile, the workflow
    # executes in the background; Temporal server takes care of delivering the eventual
    # workflow result (success or failure) to the calling workflow.
    #
    # The token will be used by the caller if it subsequently wants to cancel the Nexus
    # operation.
    @nexus.workflow_run_operation
    async def say_hello(
        self, ctx: nexus.WorkflowRunOperationContext, input: MyInput
    ) -> nexus.WorkflowHandle[MyOutput]:
        # For "retry-me": attach a retry policy so the workflow re-runs on failure.
        # Without a retry policy, even a retryable ApplicationError fails the workflow
        # immediately — Nexus doesn't add its own retries for workflow-backed operations.
        retry_policy = (
            RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
            )
            if input.name == "retry-me"
            else None
        )
        return await ctx.start_workflow(
            SayHelloWorkflow.run,
            input,
            id=str(uuid.uuid4()),
            retry_policy=retry_policy,
        )

    # This is a Nexus operation that responds synchronously to all requests. That means
    # that unlike the workflow run operation above, in this case the `start` method
    # returns the final operation result.
    #
    # Sync operations are free to make arbitrary network calls, or perform CPU-bound
    # computations. Total execution duration must not exceed 10s.
    @nexusrpc.handler.sync_operation
    async def my_sync_operation(
        self, ctx: nexusrpc.handler.StartOperationContext, input: MyInput
    ) -> MyOutput:
        return MyOutput(message=f"Hello {input.name} from sync operation!")
