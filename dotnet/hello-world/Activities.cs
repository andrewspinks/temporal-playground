using Temporalio.Activities;

namespace HelloWorld;

public class GreetingActivities
{
    [Activity]
    public string SayHello(string name) => $"Hello, {name}!";
}
