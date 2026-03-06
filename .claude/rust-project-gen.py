#!/usr/bin/env python3
"""Generate all files for a scaffolded Rust Temporal hello-world project."""
import os
import sys

project_dir = sys.argv[1]
project_name = sys.argv[2]
sdk_version = sys.argv[3]
rust_version = sys.argv[4] if len(sys.argv) > 4 else ""

crate_name = project_name.replace("-", "_")

os.makedirs(f"{project_dir}/src/bin", exist_ok=True)

# Cargo.toml
with open(f"{project_dir}/Cargo.toml", "w") as f:
    f.write(f"""\
[package]
name = "{project_name}"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "worker"
path = "src/bin/worker.rs"

[[bin]]
name = "starter"
path = "src/bin/starter.rs"

[dependencies]
temporalio-sdk = "{sdk_version}"
temporalio-client = "{sdk_version}"
temporalio-macros = "{sdk_version}"
temporalio-sdk-core = "{sdk_version}"
tokio = {{ version = "1", features = ["full"] }}
anyhow = "1"
""")

# src/lib.rs
with open(f"{project_dir}/src/lib.rs", "w") as f:
    f.write("""\
pub mod activities;
pub mod workflows;
""")

# src/activities.rs
with open(f"{project_dir}/src/activities.rs", "w") as f:
    f.write("""\
use temporalio_macros::activities;
use temporalio_sdk::activities::{ActivityContext, ActivityError};

pub struct MyActivities;

#[activities]
impl MyActivities {
    #[activity]
    pub async fn greet(_ctx: ActivityContext, name: String) -> Result<String, ActivityError> {
        println!("Greeting {name}");
        Ok(format!("Hello, {name}!"))
    }
}
""")

# src/workflows.rs
with open(f"{project_dir}/src/workflows.rs", "w") as f:
    f.write("""\
use std::time::Duration;

use temporalio_macros::{workflow, workflow_methods};
use temporalio_sdk::{ActivityOptions, WorkflowContext, WorkflowContextView, WorkflowResult};

use crate::activities::MyActivities;

#[workflow]
pub struct GreetingWorkflow {
    name: String,
}

#[workflow_methods]
impl GreetingWorkflow {
    #[init]
    fn new(_ctx: &WorkflowContextView, name: String) -> Self {
        Self { name }
    }

    #[run]
    async fn run(ctx: &mut WorkflowContext<Self>) -> WorkflowResult<String> {
        let name = ctx.state(|s| s.name.clone());
        let greeting = ctx
            .start_activity(
                MyActivities::greet,
                name,
                ActivityOptions {
                    start_to_close_timeout: Some(Duration::from_secs(10)),
                    ..Default::default()
                },
            )?
            .await?;
        Ok(greeting)
    }
}
""")

# src/bin/worker.rs
worker_rs = """\
use std::str::FromStr;

use temporalio_client::{Client, ClientOptions, Connection, ConnectionOptions};
use temporalio_sdk::{Worker, WorkerOptions};
use temporalio_sdk_core::{CoreRuntime, RuntimeOptions, Url};

use CRATE_NAME::activities::MyActivities;
use CRATE_NAME::workflows::GreetingWorkflow;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let runtime = CoreRuntime::new_assume_tokio(RuntimeOptions::builder().build()?)?;

    let connection = Connection::connect(
        ConnectionOptions::new(Url::from_str("http://localhost:7233")?).build(),
    )
    .await?;
    let client = Client::new(connection, ClientOptions::new("default").build());

    let worker_options = WorkerOptions::new("greeting-task-queue")
        .register_activities(MyActivities)
        .register_workflow::<GreetingWorkflow>()
        .build();

    println!("Starting worker on task queue 'greeting-task-queue'...");
    Worker::new(&runtime, client, worker_options)?.run().await?;
    Ok(())
}
""".replace("CRATE_NAME", crate_name)

with open(f"{project_dir}/src/bin/worker.rs", "w") as f:
    f.write(worker_rs)

# src/bin/starter.rs
starter_rs = """\
use std::str::FromStr;

use temporalio_client::{Client, ClientOptions, Connection, ConnectionOptions};
use temporalio_sdk_core::Url;

use CRATE_NAME::workflows::GreetingWorkflow;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let connection = Connection::connect(
        ConnectionOptions::new(Url::from_str("http://localhost:7233")?).build(),
    )
    .await?;
    let client = Client::new(connection, ClientOptions::new("default").build());

    let handle = client
        .start_workflow_typed::<GreetingWorkflow, _>(
            "greeting-workflow-1",
            "greeting-task-queue",
            "World".to_string(),
        )
        .await?;

    println!("Started workflow 'greeting-workflow-1'");
    let result: String = handle.result().await?;
    println!("Result: {result}");
    Ok(())
}
""".replace("CRATE_NAME", crate_name)

with open(f"{project_dir}/src/bin/starter.rs", "w") as f:
    f.write(starter_rs)

# justfile (per-project)
with open(f"{project_dir}/justfile", "w") as f:
    f.write("""\
# Run the worker
worker:
    cargo run --bin worker

# Start a workflow execution
start:
    cargo run --bin starter

# Build the project
build:
    cargo build

# Lint with Clippy
check:
    cargo clippy
""")

# rust-toolchain.toml (only if rust_version specified)
if rust_version:
    with open(f"{project_dir}/rust-toolchain.toml", "w") as f:
        f.write(f"""\
[toolchain]
channel = "{rust_version}"
""")

print(f"Generated project files in {project_dir}/")
