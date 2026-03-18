"""Tests for extract-grpc-calls.py."""

import json
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# -- Unit tests: detect_direction --


def test_detect_direction_response(extract_mod):
    assert extract_mod.detect_direction({"http2.request_in": "5"}) == "response"


def test_detect_direction_data_frame_request(extract_mod):
    assert extract_mod.detect_direction({"http2.type": "0"}) == "request"


def test_detect_direction_headers_frame_request(extract_mod):
    assert extract_mod.detect_direction({"http2.type": "1"}) == "request"


def test_detect_direction_empty(extract_mod):
    assert extract_mod.detect_direction({}) == "unknown"


def test_detect_direction_none(extract_mod):
    assert extract_mod.detect_direction(None) == "unknown"


# -- Unit tests: extract_grpc_method --


def test_extract_grpc_method_simple_uri(extract_mod):
    layer = {
        "http2.request.full_uri": "http://localhost:7233/temporal.api.workflowservice.v1.WorkflowService/GetSystemInfo"
    }
    result = extract_mod.extract_grpc_method(layer)
    assert result == "/temporal.api.workflowservice.v1.WorkflowService/GetSystemInfo"


def test_extract_grpc_method_nested_in_list(extract_mod):
    layer = {
        "http2.stream": [
            {
                "http2.request.full_uri": "http://localhost:7233/temporal.api.workflowservice.v1.WorkflowService/PollWorkflowTaskQueue"
            }
        ]
    }
    result = extract_mod.extract_grpc_method(layer)
    assert result == "/temporal.api.workflowservice.v1.WorkflowService/PollWorkflowTaskQueue"


def test_extract_grpc_method_null_uri(extract_mod):
    layer = {"http2.request.full_uri": "(null)"}
    assert extract_mod.extract_grpc_method(layer) is None


def test_extract_grpc_method_empty_dict(extract_mod):
    assert extract_mod.extract_grpc_method({}) is None


# -- E2E tests --


def test_main_pipeline(extract_mod, tmp_path, monkeypatch):
    """Run main() with raw-packets fixture, verify numbered files + summary."""
    raw_path = str(FIXTURES_DIR / "raw-packets.json")
    out_dir = str(tmp_path / "output")

    monkeypatch.setattr("sys.argv", [
        "extract-grpc-calls.py", raw_path, out_dir,
    ])

    extract_mod.main()

    # Check summary.json was created
    summary_path = os.path.join(out_dir, "summary.json")
    assert os.path.exists(summary_path)

    with open(summary_path) as f:
        summary = json.load(f)

    assert summary["total_packets"] == 3
    assert len(summary["calls"]) == 3

    # Each call should have required fields
    for call in summary["calls"]:
        assert "seq" in call
        assert "direction" in call
        assert "method" in call

    # Check numbered files exist
    numbered = [f for f in os.listdir(out_dir) if f[0].isdigit() and f.endswith(".json")]
    assert len(numbered) == summary["total_packets"]

    # Verify first call is GetSystemInfo request
    first_call = summary["calls"][0]
    assert first_call["method"] == "GetSystemInfo"
    assert first_call["direction"] == "request"

    # Verify second call is GetSystemInfo response
    second_call = summary["calls"][1]
    assert second_call["method"] == "GetSystemInfo"
    assert second_call["direction"] == "response"


def test_main_cleans_stale(extract_mod, tmp_path, monkeypatch):
    """Seed output dir with a stale file, verify it's cleaned up."""
    raw_path = str(FIXTURES_DIR / "raw-packets.json")
    out_dir = str(tmp_path / "output")
    os.makedirs(out_dir)

    # Create stale file
    stale = os.path.join(out_dir, "099-Stale-request.json")
    with open(stale, "w") as f:
        json.dump({"stale": True}, f)

    monkeypatch.setattr("sys.argv", [
        "extract-grpc-calls.py", raw_path, out_dir,
    ])

    extract_mod.main()

    assert not os.path.exists(stale)
