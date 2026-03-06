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
