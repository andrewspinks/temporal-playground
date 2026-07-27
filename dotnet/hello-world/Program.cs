using HelloWorld;
using Temporalio.Client;
using Temporalio.Worker;

const string TaskQueue = "hello-world-task-queue";
var address = Environment.GetEnvironmentVariable("TEMPORAL_ADDRESS") ?? "localhost:7233";

var client = await TemporalClient.ConnectAsync(new(address));

switch (args.FirstOrDefault())
{
    case "worker":
        await RunWorkerAsync(client);
        break;
    case "starter":
        await RunStarterAsync(client, args.Length > 1 ? args[1] : "Temporal");
        break;
    default:
        Console.Error.WriteLine("Usage: dotnet run -- [worker|starter [name]]");
        Environment.Exit(1);
        break;
}

static async Task RunWorkerAsync(ITemporalClient client)
{
    using var tokenSource = new CancellationTokenSource();
    Console.CancelKeyPress += (_, e) =>
    {
        e.Cancel = true;
        tokenSource.Cancel();
    };

    using var worker = new TemporalWorker(
        client,
        new TemporalWorkerOptions(TaskQueue)
            // .AddActivity(new GreetingActivities().SayHello)
            .AddWorkflow<JobTrackingWorkflow>());

    Console.WriteLine($"Worker started on task queue '{TaskQueue}'. Ctrl+C to exit.");
    try
    {
        await worker.ExecuteAsync(tokenSource.Token);
    }
    catch (OperationCanceledException)
    {
        Console.WriteLine("Worker shutting down.");
    }
}

static async Task RunStarterAsync(ITemporalClient client, string name)
{
    var result = await client.ExecuteWorkflowAsync(
        (JobTrackingWorkflow wf) => wf.ProcessAsync(new WorkflowStartInput()),
        new WorkflowOptions(id: "hello-world-workflow-id", taskQueue: TaskQueue));

    Console.WriteLine($"Workflow result: {result}");
}
