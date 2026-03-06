use std::str::FromStr;

use temporalio_client::{Client, ClientOptions, Connection, ConnectionOptions};
use temporalio_sdk::{Worker, WorkerOptions};
use temporalio_sdk_core::{CoreRuntime, RuntimeOptions, Url};

use hello_world::activities::MyActivities;
use hello_world::workflows::GreetingWorkflow;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let runtime = CoreRuntime::new_assume_tokio(RuntimeOptions::builder().build()?)?;

    let connection = Connection::connect(
        ConnectionOptions::new(Url::from_str("http://localhost:7233")?)
            .identity("rust-worker".to_string())
            .build(),
    )
    .await?;
    let client = Client::new(connection, ClientOptions::new("default").build())?;

    let worker_options = WorkerOptions::new("greeting-task-queue")
        .register_activities(MyActivities)
        .register_workflow::<GreetingWorkflow>()
        .build();

    println!("Starting worker on task queue 'greeting-task-queue'...");
    Worker::new(&runtime, client, worker_options)?.run().await?;
    Ok(())
}
