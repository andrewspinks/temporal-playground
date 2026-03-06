use std::str::FromStr;

use temporalio_client::{
    Client, ClientOptions, Connection, ConnectionOptions, WorkflowStartOptions,
};
use temporalio_sdk_core::{CoreRuntime, RuntimeOptions, Url};

use hello_world::workflows::GreetingWorkflow;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _runtime = CoreRuntime::new_assume_tokio(RuntimeOptions::builder().build()?)?;
    let connection = Connection::connect(
        ConnectionOptions::new(Url::from_str("http://localhost:7233")?).build(),
    )
    .await?;
    let client = Client::new(connection, ClientOptions::new("default").build())?;

    let options = WorkflowStartOptions::new("greeting-task-queue", "greeting-workflow-1").build();

    let handle = client
        .start_workflow(GreetingWorkflow, "World".to_string(), options)
        .await?;

    println!(
        "Started workflow 'greeting-workflow-1', run_id: {}",
        handle.run_id().unwrap_or("<unknown>")
    );
    Ok(())
}
