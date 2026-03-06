use hello_world::activities::MyActivities;
use hello_world::workflows::GreetingWorkflow;
use temporal_test_harness::TestWorkflowEnvironment;

#[tokio::test]
async fn test_greeting_happy_path() {
    let mut env = TestWorkflowEnvironment::new();
    env.register_activities(MyActivities);
    env.on_activity("MyActivities::greet")
        .returns("Hello, World!");

    env.execute_workflow::<GreetingWorkflow>("World".to_string())
        .await
        .expect("harness should not error");

    assert!(env.is_workflow_completed());
    assert!(env.workflow_error().is_none());
    let result: String = env.workflow_result().unwrap();
    assert_eq!(result, "Hello, World!");
}

#[tokio::test]
async fn test_greeting_activity_fails() {
    let mut env = TestWorkflowEnvironment::new();
    env.register_activities(MyActivities);
    env.on_activity("MyActivities::greet")
        .returns_err("greet service unavailable");

    env.execute_workflow::<GreetingWorkflow>("World".to_string())
        .await
        .expect("harness should not error");

    assert!(env.is_workflow_completed());
    assert!(env.workflow_error().is_some());
}
