use std::time::Duration;

use temporalio_macros::{workflow, workflow_methods};
use temporalio_sdk::{ActivityOptions, WorkflowContext, WorkflowResult};

use crate::activities::MyActivities;

#[workflow]
#[derive(Default)]
pub struct GreetingWorkflow;

#[workflow_methods]
impl GreetingWorkflow {
    #[run]
    pub async fn run(ctx: &mut WorkflowContext<Self>, name: String) -> WorkflowResult<String> {
        let greeting = ctx
            .start_activity(
                MyActivities::greet,
                name,
                ActivityOptions {
                    start_to_close_timeout: Some(Duration::from_secs(10)),
                    ..Default::default()
                },
            )
            .await?;
        Ok(greeting)
    }
}
