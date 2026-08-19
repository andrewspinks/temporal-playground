"""Payload decoding.

Handles every payload encoding these histories use:
  - json/plain      -> Python dict/list/scalar (WCI args/state, PullStats results)
  - binary/protobuf -> proto Message (server-internal deployment/version state),
                       decoded via the committed FileDescriptorSet
  - json/protobuf   -> proto Message
  - binary/plain    -> bytes
  - binary/null     -> None
"""
from __future__ import annotations

import functools
import json
import os

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

_DESC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "descriptors", "deployment_descriptors.binpb"
)


@functools.lru_cache(maxsize=1)
def _pool() -> descriptor_pool.DescriptorPool:
    fds = descriptor_pb2.FileDescriptorSet()
    with open(_DESC_PATH, "rb") as fh:
        fds.ParseFromString(fh.read())
    pool = descriptor_pool.DescriptorPool()
    for f in fds.file:  # already topologically ordered by gen_descriptors.go
        pool.Add(f)
    return pool


@functools.lru_cache(maxsize=None)
def message_class(full_name: str):
    return message_factory.GetMessageClass(_pool().FindMessageTypeByName(full_name))


def _meta(payload, key: str) -> str:
    v = payload.metadata.get(key)
    return v.decode() if v is not None else ""


def decode_payload(payload):
    """Decode a temporalio.api.common.v1.Payload into a native value or proto."""
    enc = _meta(payload, "encoding")
    data = payload.data
    if enc == "binary/null":
        return None
    if enc == "json/plain":
        return json.loads(data) if data else None
    if enc == "binary/plain":
        return bytes(data)
    if enc in ("binary/protobuf", "json/protobuf"):
        mt = _meta(payload, "messageType")
        if not mt:
            return bytes(data)
        try:
            Msg = message_class(mt)
        except KeyError:
            # A message type outside our bundled descriptors (e.g. an unrelated
            # server proto in a signal payload). We only decode the types we own.
            return {"_undecoded_messageType": mt}
        msg = Msg()
        if enc == "binary/protobuf":
            msg.ParseFromString(data)
        else:
            from google.protobuf import json_format

            json_format.Parse(bytes(data).decode(), msg, ignore_unknown_fields=True)
        return msg
    # Unknown encoding: best-effort.
    try:
        return json.loads(data)
    except Exception:
        return bytes(data)


def decode_first(payloads):
    """Decode the first payload of a Payloads collection (or None)."""
    return decode_payload(payloads[0]) if payloads else None
