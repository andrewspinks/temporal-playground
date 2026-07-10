from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.agent import AnalysisResult, temporal_agent


@workflow.defn
class DocAnalysisWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> AnalysisResult:
        # temporal_agent.run drives the agent loop deterministically: every
        # model call and every tool call is offloaded to an activity. The
        # workflow itself stays deterministic and does no I/O.
        #
        # This single line is the whole repro: with each turn, the growing
        # message history is re-sent as the next model_request activity's
        # input, inflating the event history.
        result = await temporal_agent.run(prompt)
        return result.output
