#!/usr/bin/env python3
"""Extract gRPC calls from tshark JSON output into per-method JSON files
with full protobuf decoding using a compiled descriptor set.

Usage: python3 extract-grpc-calls.py <raw.json> <output-dir> [descriptor.binpb] [server-port]

Produces:
  <output-dir>/001-StartWorkflowExecution-request.json
  <output-dir>/002-StartWorkflowExecution-response.json
  ...
  <output-dir>/summary.json
"""

import json
import os
import sys

from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from google.protobuf.json_format import MessageToDict

DEFAULT_SERVER_PORT = "7233"


def load_descriptor_pool(binpb_path):
    """Load a compiled FileDescriptorSet into a descriptor pool."""
    fds = descriptor_pb2.FileDescriptorSet()
    with open(binpb_path, "rb") as f:
        fds.ParseFromString(f.read())

    pool = descriptor_pool.DescriptorPool()
    # Add files in dependency order (buf build already sorts them)
    added = set()

    def add_file(fd_proto):
        if fd_proto.name in added:
            return
        for dep in fd_proto.dependency:
            # Find the dep in the set
            for other in fds.file:
                if other.name == dep:
                    add_file(other)
                    break
        try:
            pool.Add(fd_proto)
        except Exception:
            pass  # already added or built-in
        added.add(fd_proto.name)

    for fd_proto in fds.file:
        add_file(fd_proto)

    return pool


def build_method_map(pool, fds_path):
    """Build a map of gRPC method path → (request_type, response_type)."""
    fds = descriptor_pb2.FileDescriptorSet()
    with open(fds_path, "rb") as f:
        fds.ParseFromString(f.read())

    method_map = {}
    for fd_proto in fds.file:
        for svc in fd_proto.service:
            for method in svc.method:
                path = f"/{fd_proto.package}.{svc.name}/{method.name}"
                req_type = method.input_type.lstrip(".")
                resp_type = method.output_type.lstrip(".")
                method_map[path] = (req_type, resp_type)

    return method_map


def decode_protobuf(pool, type_name, raw_hex):
    """Decode a hex-encoded protobuf message using the descriptor pool."""
    try:
        descriptor = pool.FindMessageTypeByName(type_name)
        msg_class = GetMessageClass(descriptor)
        raw_bytes = bytes.fromhex(raw_hex.replace(":", ""))
        msg = msg_class()
        msg.ParseFromString(raw_bytes)
        return MessageToDict(msg, preserving_proto_field_name=True)
    except Exception as e:
        return {"_decode_error": str(e)}


def extract_grpc_method(http2_layer):
    """Extract the gRPC method path from http2.request.full_uri."""
    def search(obj):
        if isinstance(obj, dict):
            uri = obj.get("http2.request.full_uri", "")
            if uri and "(null)" not in uri:
                idx = uri.find("/", uri.find("//") + 2)
                if idx >= 0:
                    path = uri[idx:]
                    if "/" in path[1:]:
                        return path
            for v in obj.values():
                result = search(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = search(item)
                if result:
                    return result
        return None

    return search(http2_layer)


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <raw.json> <output-dir> [descriptor.binpb]")
        sys.exit(1)

    raw_path = sys.argv[1]
    output_dir = sys.argv[2]
    binpb_path = sys.argv[3] if len(sys.argv) > 3 else None
    server_port = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_SERVER_PORT

    os.makedirs(output_dir, exist_ok=True)

    # Clean up old numbered JSON files and summary from previous runs
    import glob
    for old_file in glob.glob(os.path.join(output_dir, "[0-9]*.json")):
        os.remove(old_file)
    summary_file = os.path.join(output_dir, "summary.json")
    if os.path.exists(summary_file):
        os.remove(summary_file)

    # Load protobuf descriptors if available
    pool = None
    method_map = {}
    if binpb_path and os.path.exists(binpb_path):
        pool = load_descriptor_pool(binpb_path)
        method_map = build_method_map(pool, binpb_path)
        print(f"Loaded {len(method_map)} gRPC method definitions from {binpb_path}")

    with open(raw_path) as f:
        packets = json.load(f)

    # First pass: build (tcp_stream, stream_id) → method map
    stream_methods = {}
    for pkt in packets:
        layers = pkt["_source"]["layers"]
        http2 = layers.get("http2", {})
        tcp = layers.get("tcp", {})
        stream = http2.get("http2.stream", {})
        stream_id = stream.get("http2.streamid")
        tcp_stream = tcp.get("tcp.stream", "")
        method = extract_grpc_method(http2)
        if stream_id and method:
            stream_methods[(tcp_stream, stream_id)] = method

    # Second pass: extract all gRPC packets with decoded payloads
    calls = []
    seq = 0

    for pkt in packets:
        layers = pkt["_source"]["layers"]
        http2 = layers.get("http2", {})
        grpc = layers.get("grpc", {})
        tcp = layers.get("tcp", {})
        frame = layers.get("frame", {})

        stream = http2.get("http2.stream", {})
        stream_id = stream.get("http2.streamid")
        frame_type = stream.get("http2.type", "")

        msg_len = grpc.get("grpc.message_length", "0")
        if msg_len == "0" and frame_type == "1":
            continue

        tcp_stream = tcp.get("tcp.stream", "")
        method = extract_grpc_method(http2) or stream_methods.get((tcp_stream, stream_id))
        if not method:
            continue

        src_port = tcp.get("tcp.srcport", "")
        dst_port = tcp.get("tcp.dstport", "")
        if dst_port == server_port:
            direction = "request"
        elif src_port == server_port:
            direction = "response"
        else:
            direction = "unknown"

        parts = method.rstrip("/").split("/")
        method_name = parts[-1] if parts else method

        timestamp = frame.get("frame.time_relative", "0")

        # Decode the protobuf payload
        raw_hex = grpc.get("grpc.message_data", "")
        decoded = None
        if pool and method in method_map and raw_hex:
            req_type, resp_type = method_map[method]
            type_name = req_type if direction == "request" else resp_type
            decoded = decode_protobuf(pool, type_name, raw_hex)

        tcp_stream = tcp.get("tcp.stream", "")

        seq += 1
        call = {
            "seq": seq,
            "timestamp": timestamp,
            "tcp_stream": tcp_stream,
            "stream_id": stream_id,
            "direction": direction,
            "method": method,
            "method_name": method_name,
            "grpc_message_length": msg_len,
            "payload": decoded,
        }
        calls.append(call)

        filename = f"{seq:03d}-{method_name}-{direction}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(call, f, indent=2)

    # Write summary
    summary = {
        "total_packets": len(calls),
        "methods": list(dict.fromkeys(c["method"] for c in calls)),
        "calls": [
            {
                "seq": c["seq"],
                "timestamp": c["timestamp"],
                "direction": c["direction"],
                "method": c["method_name"],
                "msg_len": c["grpc_message_length"],
            }
            for c in calls
        ],
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Extracted {len(calls)} gRPC packets across {len(summary['methods'])} methods")
    for method in summary["methods"]:
        req = sum(1 for c in calls if c["method"] == method and c["direction"] == "request")
        resp = sum(1 for c in calls if c["method"] == method and c["direction"] == "response")
        short = method.split("/")[-1]
        print(f"  {short}: {req} request(s), {resp} response(s)")


if __name__ == "__main__":
    main()
