"""Tests for analyze-queues.py."""


# -- Unit tests: extract_wft_detail --


def test_wft_detail_first_wft_started_trigger(analyze_mod):
    """First WFT — STARTED is the trigger, no prior WFT_COMPLETED."""
    payload = {
        "history": {
            "events": [
                {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                {"event_id": "2", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "3", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    triggers, coalesced = analyze_mod.extract_wft_detail(payload)
    assert triggers == ["Workflow Execution Started"]
    assert coalesced is False


def test_wft_detail_signal_trigger(analyze_mod):
    """Signal after WFT_COMPLETED triggers a new WFT."""
    payload = {
        "history": {
            "events": [
                {"event_id": "4", "event_type": "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"},
                {"event_id": "5", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED"},
                {"event_id": "6", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "7", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    triggers, coalesced = analyze_mod.extract_wft_detail(payload)
    assert triggers == ["Workflow Execution Signaled"]
    assert coalesced is False


def test_wft_detail_coalesced(analyze_mod):
    """Multiple triggers coalesced into one WFT."""
    payload = {
        "history": {
            "events": [
                {"event_id": "4", "event_type": "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"},
                {"event_id": "5", "event_type": "EVENT_TYPE_TIMER_FIRED"},
                {"event_id": "6", "event_type": "EVENT_TYPE_ACTIVITY_TASK_COMPLETED"},
                {"event_id": "7", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "8", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    triggers, coalesced = analyze_mod.extract_wft_detail(payload)
    assert len(triggers) == 2
    assert "Timer Fired" in triggers
    assert "Activity Task Completed" in triggers
    assert coalesced is True


def test_wft_detail_empty_payload(analyze_mod):
    triggers, coalesced = analyze_mod.extract_wft_detail({})
    assert triggers == []
    assert coalesced is False


# -- Unit tests: detect_replay --


def test_detect_replay_full_history_with_completions(analyze_mod):
    """Full history starting at event_id 1 with 2 WFT_COMPLETED = replay."""
    payload = {
        "history": {
            "events": [
                {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                {"event_id": "2", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "3", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
                {"event_id": "4", "event_type": "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"},
                {"event_id": "5", "event_type": "EVENT_TYPE_TIMER_FIRED"},
                {"event_id": "6", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "7", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
                {"event_id": "8", "event_type": "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"},
                {"event_id": "9", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "10", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    is_replay, count = analyze_mod.detect_replay(payload)
    assert is_replay is True
    assert count == 2


def test_detect_replay_first_wft(analyze_mod):
    """First WFT — no prior completions, not a replay."""
    payload = {
        "history": {
            "events": [
                {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                {"event_id": "2", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "3", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    is_replay, count = analyze_mod.detect_replay(payload)
    assert is_replay is False
    assert count == 0


def test_detect_replay_incremental_history(analyze_mod):
    """Incremental history (event_id > 1) — not a replay."""
    payload = {
        "history": {
            "events": [
                {"event_id": "5", "event_type": "EVENT_TYPE_TIMER_FIRED"},
                {"event_id": "6", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "7", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        }
    }
    is_replay, count = analyze_mod.detect_replay(payload)
    assert is_replay is False
    assert count == 0


def test_detect_replay_empty_payload(analyze_mod):
    is_replay, count = analyze_mod.detect_replay({})
    assert is_replay is False
    assert count == 0


# -- Unit tests: build_task --


def test_build_task_workflow(analyze_mod):
    payload = {
        "workflow_execution": {"workflow_id": "wf-1", "run_id": "run-1"},
        "workflow_type": {"name": "MyWorkflow"},
        "attempt": 1,
        "history": {
            "events": [
                {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                {"event_id": "2", "event_type": "EVENT_TYPE_WORKFLOW_TASK_SCHEDULED"},
                {"event_id": "3", "event_type": "EVENT_TYPE_WORKFLOW_TASK_STARTED"},
            ]
        },
    }
    task = analyze_mod.build_task("PollWorkflowTaskQueue", payload, 10)
    assert task["type"] == "Workflow"
    assert task["seq"] == 10
    assert task["workflow_type"] == "MyWorkflow"
    assert task["workflow_id"] == "wf-1"
    assert task["run_id"] == "run-1"
    assert task["replay"] is False
    assert "Workflow Execution Started" in task["triggers"]


def test_build_task_activity(analyze_mod):
    payload = {
        "activity_type": {"name": "SendEmail"},
        "activity_id": "42",
        "workflow_type": {"name": "MyWorkflow"},
        "workflow_execution": {"workflow_id": "wf-1", "run_id": "run-1"},
        "attempt": 2,
    }
    task = analyze_mod.build_task("PollActivityTaskQueue", payload, 20)
    assert task["type"] == "Activity"
    assert task["seq"] == 20
    assert task["activity_type"] == "SendEmail"
    assert task["activity_id"] == "42"
    assert task["attempt"] == 2


# -- E2E tests --


def test_analyze_queues_basic(analyze_mod, sample_calls_dir):
    output = analyze_mod.analyze_queues(sample_calls_dir)
    assert "test-queue" in output
    assert "Workflow task" in output
    assert "Activity task" in output
    assert "greetActivity" in output
    assert "1234@test-host" in output


def test_analyze_queues_replay(analyze_mod, replay_calls_dir):
    output = analyze_mod.analyze_queues(replay_calls_dir)
    assert "REPLAY" in output
    assert "replay-queue" in output
    assert "ReplayWorkflow" in output
