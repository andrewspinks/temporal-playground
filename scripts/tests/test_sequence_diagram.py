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


def test_extract_detail_start_workflow_eager_requested(sequence_mod):
    detail = {
        "payload": {
            "workflow_type": {"name": "MyWorkflow"},
            "workflow_id": "wf-123",
            "request_eager_execution": True,
        }
    }
    result = sequence_mod.extract_detail("StartWorkflowExecution", detail)
    assert "[eager-requested]" in result
    assert "MyWorkflow" in result


def test_extract_detail_start_workflow_not_eager(sequence_mod):
    detail = {
        "payload": {
            "workflow_type": {"name": "MyWorkflow"},
            "workflow_id": "wf-123",
        }
    }
    result = sequence_mod.extract_detail("StartWorkflowExecution", detail)
    assert "eager" not in result


def test_extract_detail_respond_completed_eager_activity(sequence_mod):
    detail = {
        "payload": {
            "commands": [
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {
                        "request_eager_execution": True,
                    },
                },
                {"command_type": "COMMAND_TYPE_START_TIMER"},
            ]
        }
    }
    result = sequence_mod.extract_detail("RespondWorkflowTaskCompleted", detail)
    assert "SCHEDULE_ACTIVITY_TASK (eager)" in result
    assert "START_TIMER" in result


def test_extract_detail_respond_completed_not_eager_activity(sequence_mod):
    detail = {
        "payload": {
            "commands": [
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {},
                },
            ]
        }
    }
    result = sequence_mod.extract_detail("RespondWorkflowTaskCompleted", detail)
    assert "SCHEDULE_ACTIVITY_TASK" in result
    assert "(eager)" not in result


def test_extract_detail_unknown_method(sequence_mod):
    result = sequence_mod.extract_detail("SomeUnknownMethod", {"payload": {}})
    assert result == ""


# -- Unit tests: extract_response_detail --


def test_response_detail_eager_wft_delivered(sequence_mod):
    detail = {
        "payload": {
            "eager_workflow_task": {
                "task_token": "abc",
                "workflow_execution": {"workflow_id": "wf-1"},
            }
        }
    }
    result = sequence_mod.extract_response_detail("StartWorkflowExecution", detail)
    assert "eager WFT delivered" in result


def test_response_detail_no_eager_wft(sequence_mod):
    detail = {"payload": {"run_id": "run-1"}}
    result = sequence_mod.extract_response_detail("StartWorkflowExecution", detail)
    assert result == ""


def test_response_detail_eager_activity_tasks(sequence_mod):
    detail = {
        "payload": {
            "activity_tasks": [
                {"activity_type": {"name": "DoWork"}, "activity_id": "1"},
                {"activity_type": {"name": "DoWork"}, "activity_id": "2"},
            ]
        }
    }
    result = sequence_mod.extract_response_detail("RespondWorkflowTaskCompleted", detail)
    assert "2 eager activity tasks delivered" in result


def test_response_detail_single_eager_activity_task(sequence_mod):
    detail = {
        "payload": {
            "activity_tasks": [
                {"activity_type": {"name": "DoWork"}, "activity_id": "1"},
            ]
        }
    }
    result = sequence_mod.extract_response_detail("RespondWorkflowTaskCompleted", detail)
    assert "1 eager activity task delivered" in result


def test_response_detail_no_eager_activity_tasks(sequence_mod):
    detail = {"payload": {"workflow_task": {"task_token": "abc"}}}
    result = sequence_mod.extract_response_detail("RespondWorkflowTaskCompleted", detail)
    assert result == ""


def test_response_detail_none(sequence_mod):
    result = sequence_mod.extract_response_detail("SomeMethod", None)
    assert result == ""


# -- Unit tests: infer_transfer_queue_arrows --


def test_infer_start_workflow_response_adds_wft(sequence_mod):
    """StartWorkflowExecution response infers History→Matching AddWorkflowTask."""
    detail = {"payload": {"run_id": "run-1"}, "grpc_message_length": "40"}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "StartWorkflowExecution", detail, "response"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert pos == "after"
    assert "AddWorkflowTask" in line
    assert "transfer queue" in line


def test_infer_start_workflow_eager_skips_matching(sequence_mod):
    """StartWorkflowExecution with eager WFT notes that Matching was skipped."""
    detail = {"payload": {"eager_workflow_task": {"task_token": "abc"}}}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "StartWorkflowExecution", detail, "response"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert "skipped Matching" in line


def test_infer_respond_completed_activity_commands(sequence_mod):
    """RespondWorkflowTaskCompleted with activity commands infers AddActivityTask."""
    detail = {
        "payload": {
            "commands": [
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {},
                },
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {},
                },
            ]
        }
    }
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "RespondWorkflowTaskCompleted", detail, "request"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert pos == "after"
    assert "2x AddActivityTask" in line
    assert "transfer queue" in line


def test_infer_respond_completed_eager_activity(sequence_mod):
    """Eager activity requests get a note instead of a transfer queue arrow."""
    detail = {
        "payload": {
            "commands": [
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {
                        "request_eager_execution": True,
                    },
                },
            ]
        }
    }
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "RespondWorkflowTaskCompleted", detail, "request"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert "eager-requested" in line
    assert "may skip Matching" in line


def test_infer_respond_completed_child_workflow(sequence_mod):
    """START_CHILD_WORKFLOW_EXECUTION infers AddWorkflowTask for child."""
    detail = {
        "payload": {
            "commands": [
                {"command_type": "COMMAND_TYPE_START_CHILD_WORKFLOW_EXECUTION"},
            ]
        }
    }
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "RespondWorkflowTaskCompleted", detail, "request"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert "AddWorkflowTask (child)" in line


def test_infer_respond_completed_mixed_commands(sequence_mod):
    """Mix of activities, eager activities, and children produces correct arrows."""
    detail = {
        "payload": {
            "commands": [
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {},
                },
                {
                    "command_type": "COMMAND_TYPE_SCHEDULE_ACTIVITY_TASK",
                    "schedule_activity_task_command_attributes": {
                        "request_eager_execution": True,
                    },
                },
                {"command_type": "COMMAND_TYPE_START_CHILD_WORKFLOW_EXECUTION"},
                {"command_type": "COMMAND_TYPE_START_TIMER"},
            ]
        }
    }
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "RespondWorkflowTaskCompleted", detail, "request"
    )
    # 1 non-eager activity → AddActivityTask, 1 eager → note, 1 child → AddWorkflowTask
    assert len(arrows) == 3
    texts = [line for _, line in arrows]
    assert any("AddActivityTask" in t and "transfer queue" in t for t in texts)
    assert any("eager-requested" in t for t in texts)
    assert any("AddWorkflowTask (child)" in t for t in texts)


def test_infer_poll_wft_delivery_record_started(sequence_mod):
    """PollWorkflowTaskQueue delivery infers Matching→History RecordWorkflowTaskStarted."""
    detail = {"payload": {}, "grpc_message_length": "500"}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "PollWorkflowTaskQueue", detail, "response"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert pos == "before"
    assert "RecordWorkflowTaskStarted" in line


def test_infer_poll_activity_delivery_record_started(sequence_mod):
    """PollActivityTaskQueue delivery infers Matching→History RecordActivityTaskStarted."""
    detail = {"payload": {}, "grpc_message_length": "300"}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "PollActivityTaskQueue", detail, "response"
    )
    assert len(arrows) == 1
    pos, line = arrows[0]
    assert pos == "before"
    assert "RecordActivityTaskStarted" in line


def test_infer_empty_poll_no_arrows(sequence_mod):
    """Empty poll response produces no inferred arrows."""
    detail = {"payload": {}, "grpc_message_length": "0"}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "PollWorkflowTaskQueue", detail, "response"
    )
    assert arrows == []


def test_infer_unrelated_method_no_arrows(sequence_mod):
    """Methods without inferred flows produce no arrows."""
    detail = {"payload": {}}
    arrows = sequence_mod.infer_transfer_queue_arrows(
        "GetSystemInfo", detail, "response"
    )
    assert arrows == []


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
