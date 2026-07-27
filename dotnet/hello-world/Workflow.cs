using Temporalio.Workflows;

namespace HelloWorld;

[Workflow]
public class SayHelloWorkflow
{
    [WorkflowRun]
    public async Task<string> RunAsync(string name)
    {
        return await Workflow.ExecuteActivityAsync(
            (GreetingActivities act) => act.SayHello(name),
            new ActivityOptions { StartToCloseTimeout = TimeSpan.FromMinutes(5) });
    }
}
