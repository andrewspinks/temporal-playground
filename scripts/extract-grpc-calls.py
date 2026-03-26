#!/usr/bin/env python3
"""Extract gRPC calls from a pcapng capture into per-method JSON files
with full protobuf decoding using a compiled descriptor set.

Usage: python3 extract-grpc-calls.py <capture.pcapng> <output-dir> [descriptor.binpb] [port]

Produces:
  <output-dir>/001-StartWorkflowExecution-request.json
  <output-dir>/002-StartWorkflowExecution-response.json
  ...
  <output-dir>/summary.json
  <output-dir>/raw.json
"""

import glob
import json
import os
import subprocess
import sys

from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from google.protobuf.json_format import MessageToDict


def load_descriptor_pool(binpb_path):
    """Load a compiled FileDescriptorSet into a descriptor pool."""
    fds = descriptor_pb2.FileDescriptorSet()
    with open(binpb_path, "rb") as f:
        fds.ParseFromString(f.read())

    pool = descriptor_pool.DescriptorPool()
    added = set()

    def add_file(fd_proto):
        if fd_proto.name in added:
            return
        for dep in fd_proto.dependency:
            for other in fds.file:
                if other.name == dep:
                    add_file(other)
                    break
        try:
            pool.Add(fd_proto)
        except Exception:
            pass
        added.add(fd_proto.name)

    for fd_proto in fds.file:
        add_file(fd_proto)

    return pool


def build_method_map(pool, fds_path):
    """Build a map of gRPC method path -> (request_type, response_type)."""
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


def detect_direction(http2_stream):
    """Detect request vs response from tshark's HTTP/2 reassembly.

    tshark adds 'http2.request_in' to response frames, linking them back to the
    request frame number. This works regardless of port numbers or proxies
    (Docker, etc.) because it's based on HTTP/2 stream state, not network topology.

    Returns 'request', 'response', or 'unknown'.
    """
    if not http2_stream:
        return "unknown"
    if http2_stream.get("http2.request_in"):
        return "response"
    # DATA frames (type 0) without request_in are requests.
    # HEADERS-only frames (type 1) without request_in are request headers
    # (the initial HEADERS frame that opens the stream).
    frame_type = http2_stream.get("http2.type", "")
    if frame_type in ("0", "1"):
        return "request"
    return "unknown"


def extract_grpc_payload(grpc_layer, http2_stream):
    """Extract gRPC message hex data and length from either grpc or http2 layer.

    tshark often doesn't tag HTTP/2 DATA frames with the grpc dissector, so we
    fall back to parsing the raw http2.data.data which contains the gRPC
    length-prefixed message (1 byte compressed flag + 4 bytes length + payload).
    """
    # Prefer the grpc dissector if available
    raw_hex = grpc_layer.get("grpc.message_data", "")
    msg_len = grpc_layer.get("grpc.message_length", "")
    if raw_hex:
        return raw_hex, msg_len or str(len(bytes.fromhex(raw_hex.replace(":", ""))))

    # Fall back to raw HTTP/2 DATA frame
    data_hex = http2_stream.get("http2.data.data", "")
    if not data_hex:
        return "", "0"

    raw_bytes = bytes.fromhex(data_hex.replace(":", ""))
    if len(raw_bytes) < 5:
        return "", "0"

    # gRPC wire format: 1 byte compressed flag + 4 bytes big-endian message length
    payload_len = int.from_bytes(raw_bytes[1:5], "big")
    payload_hex = raw_bytes[5:5 + payload_len].hex()
    # Format as colon-separated hex to match tshark's grpc.message_data format
    payload_hex = ":".join(payload_hex[i:i+2] for i in range(0, len(payload_hex), 2))
    return payload_hex, str(payload_len)


def build_stream_method_map_from_tshark(pcapng_path, port):
    """Use tshark -T fields to reliably extract the (tcp_stream, http2_stream) -> method map.

    tshark's JSON export loses :path headers when HEADERS and DATA frames share
    a TCP segment.  The -T fields output is reliable because tshark prints each
    HTTP/2 frame separately.
    """
    result = subprocess.run(
        [
            "tshark",
            "-r", pcapng_path,
            "-d", f"tcp.port=={port},http2",
            "-Y", 'http2.header.name==":path"',
            "-T", "fields",
            "-e", "tcp.stream",
            "-e", "http2.streamid",
            "-e", "http2.header.value",
            "-E", "separator=|",
        ],
        capture_output=True, text=True,
    )

    stream_methods = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        tcp_stream = parts[0]
        # http2.streamid can be comma-separated when multiple frames are in one packet
        stream_ids = parts[1].split(",")
        # header values are also comma-separated; find the :path value
        values = parts[2].split(",")
        path = None
        for v in values:
            v = v.strip()
            if v.startswith("/") and "/" in v[1:]:
                path = v
                break
        if path:
            for sid in stream_ids:
                sid = sid.strip()
                if sid:
                    stream_methods[(tcp_stream, sid)] = path

    return stream_methods


def export_raw_json(pcapng_path, port, output_path):
    """Run tshark to export HTTP/2 DATA and HEADERS frames as JSON."""
    result = subprocess.run(
        [
            "tshark",
            "-r", pcapng_path,
            "-d", f"tcp.port=={port},http2",
            "-Y", "http2.type==0 || http2.type==1",
            "-T", "json",
        ],
        capture_output=True, text=True,
    )
    with open(output_path, "w") as f:
        f.write(result.stdout)
    return json.loads(result.stdout)


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <capture.pcapng> <output-dir> [descriptor.binpb] [port]")
        sys.exit(1)

    pcapng_path = sys.argv[1]
    output_dir = sys.argv[2]
    binpb_path = sys.argv[3] if len(sys.argv) > 3 else None
    port = sys.argv[4] if len(sys.argv) > 4 else "7233"

    os.makedirs(output_dir, exist_ok=True)

    # Clean up old numbered JSON files and summary from previous runs
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

    # Step 1: Build stream -> method map using tshark -T fields (reliable for :path headers)
    print("Building stream method map...")
    stream_methods = build_stream_method_map_from_tshark(pcapng_path, port)
    print(f"Found {len(stream_methods)} stream->method mappings")

    # Step 2: Export HTTP/2 frames as JSON for payload extraction
    raw_json_path = os.path.join(output_dir, "raw.json")
    print("Exporting HTTP/2 frames...")
    packets = export_raw_json(pcapng_path, port, raw_json_path)
    print(f"Exported {len(packets)} HTTP/2 packets")

    # Also pick up any methods visible in the JSON (supplements the fields-based map)
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

    # Extract all gRPC calls with decoded payloads
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

        # Only process DATA (0) and HEADERS (1) frames
        if frame_type not in ("0", "1"):
            continue

        raw_hex, msg_len = extract_grpc_payload(grpc, stream)

        # Skip HEADERS-only frames with no payload data
        if not raw_hex and frame_type == "1":
            continue

        tcp_stream = tcp.get("tcp.stream", "")
        method = extract_grpc_method(http2) or stream_methods.get((tcp_stream, stream_id))
        if not method:
            continue

        direction = detect_direction(stream)

        parts = method.rstrip("/").split("/")
        method_name = parts[-1] if parts else method

        timestamp = frame.get("frame.time_relative", "0")

        # Decode the protobuf payload
        decoded = None
        if pool and method in method_map and raw_hex:
            req_type, resp_type = method_map[method]
            type_name = req_type if direction == "request" else resp_type
            decoded = decode_protobuf(pool, type_name, raw_hex)

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
