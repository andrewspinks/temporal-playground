"""Tests for sequence-diagram.py."""


# -- Unit tests: extract_detail --


def test_extract_detail_start_workflow(sequence_mod):
    detail = {
        "payload": {
            "workflow_type": {"name": "MyWorkflow"},
            "workflow_id": "wf-123",
        }
    }
    result = sequence_mod.extract_detail("StartWorkflowExecution", detail)
    assert "MyWorkflow" in result
    assert "wf-123" in result


def test_extract_detail_respond_completed_with_commands(sequence_mod):
    detail = {
        "payload": {
            "commands": [
                {"command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK"},
                {"command_type": "COMMAND_TYPE_START_TIMER"},
            ]
        }
    }
    result = sequence_mod.extract_detail("RespondWorkflowTaskCompleted", detail)
    assert "SCHEDULE_ACTIVITY_TASK" in result
    assert "START_TIMER" in result


def test_extract_detail_unknown_method(sequence_mod):
    result = sequence_mod.extract_detail("SomeUnknownMethod", {"payload": {}})
    assert result == ""


# -- Unit tests: detect_replay --


def test_detect_replay_true(sequence_mod):
    detail = {
        "payload": {
            "history": {
                "events": [
                    {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                    {"event_id": "2", "event_type": "EVENT_TYPE_WORKFLOW_TASK_COMPLETED"},
                ]
            }
        }
    }
    assert sequence_mod.detect_replay(detail) is True


def test_detect_replay_false_no_completed(sequence_mod):
    detail = {
        "payload": {
            "history": {
                "events": [
                    {"event_id": "1", "event_type": "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"},
                ]
            }
        }
    }
    assert sequence_mod.detect_replay(detail) is False


def test_detect_replay_none(sequence_mod):
    assert sequence_mod.detect_replay(None) is False


# -- Unit tests: extract_identity --


def test_extract_identity_top_level(sequence_mod):
    assert sequence_mod.extract_identity({"identity": "worker@host"}) == "worker@host"


def test_extract_identity_nested_in_meta(sequence_mod):
    payload = {"request": {"meta": {"identity": "starter@host"}}}
    assert sequence_mod.extract_identity(payload) == "starter@host"


def test_extract_identity_none(sequence_mod):
    assert sequence_mod.extract_identity(None) == ""


# -- Unit tests: classify_calls --


def test_classify_calls_starter_and_worker(sequence_mod):
    summary_calls = [
        {"seq": 1, "method": "GetSystemInfo", "direction": "request", "msg_len": "0"},
        {"seq": 5, "method": "StartWorkflowExecution", "direction": "request", "msg_len": "100"},
        {"seq": 3, "method": "PollWorkflowTaskQueue", "direction": "request", "msg_len": "150"},
    ]
    details = {
        1: {
            "tcp_stream": "0",
            "payload": {"identity": "worker@host", "namespace": "default"},
            "method_name": "GetSystemInfo",
        },
        5: {
            "tcp_stream": "1",
            "payload": {"identity": "starter@host", "namespace": "default",
                        "workflow_type": {"name": "W"}, "workflow_id": "wf-1"},
            "method_name": "StartWorkflowExecution",
        },
        3: {
            "tcp_stream": "0",
            "payload": {"identity": "worker@host", "namespace": "default",
                        "task_queue": {"name": "q"}},
            "method_name": "PollWorkflowTaskQueue",
        },
    }
    seq_role, seq_identity = sequence_mod.classify_calls(summary_calls, details)
    assert seq_role[5] == "starter"
    assert seq_role[3] == "worker"
    assert seq_identity[5] == "starter@host"
    assert seq_identity[3] == "worker@host"


# -- E2E tests --


def test_diagram_simplified(sequence_mod, sample_calls_dir):
    diagram = sequence_mod.generate_diagram(sample_calls_dir)
    assert diagram.startswith("sequenceDiagram")
    assert "Server" in diagram
    # Polls should be collapsed into notes in simplified mode
    assert "PollWorkflowTaskQueue" in diagram
    # StartWorkflowExecution should appear as a labeled arrow
    assert "StartWorkflowExecution" in diagram


def test_diagram_raw(sequence_mod, sample_calls_dir):
    diagram = sequence_mod.generate_diagram(sample_calls_dir, raw_mode=True)
    assert diagram.startswith("sequenceDiagram")
    # Raw mode shows activation markers
    assert "->>" in diagram


def test_diagram_replay(sequence_mod, replay_calls_dir):
    diagram = sequence_mod.generate_diagram(replay_calls_dir)
    assert "REPLAY" in diagram
