"""A tiny in-memory stand-in for a key management service (KMS).

In production these keys would live in a KMS / secrets manager and be fetched
on demand; here we just hold them in a dict. Each key is 32 bytes (AES-256).

The KEYRING is the *history* of keys: every key we have ever encrypted with.
Long-lived components (the worker, any process that reads old data) should hold
the full keyring so they can decrypt anything. To rotate, you add a new key and
point new encryption at it via ``active_key_id`` -- you do NOT remove old keys.
"""

import dataclasses
from typing import Dict, Optional

import temporalio.converter
from temporalio.client import Client
from temporalio.envconfig import ClientConfig

from app.codec import RotatingEncryptionCodec

TASK_QUEUE = "encryption-key-rotation-task-queue"

# Every key we have ever used, oldest first. `b"key-2024" * 4` is 32 bytes.
KEYRING: Dict[str, bytes] = {
    "key-2024": b"key-2024" * 4,
    "key-2025": b"key-2025" * 4,
}

# The newest key -- what a fully rotated deployment encrypts with today.
CURRENT_KEY_ID = "key-2025"


async def connect(
    active_key_id: str, keyring: Optional[Dict[str, bytes]] = None
) -> Client:
    """Connect a Temporal client whose codec encrypts with ``active_key_id`` and
    can decrypt anything in ``keyring`` (defaults to the full KEYRING)."""
    if keyring is None:
        keyring = KEYRING
    config = ClientConfig.load_client_connect_config()
    config.setdefault("target_host", "localhost:7233")
    return await Client.connect(
        **config,
        # Keep the default converter, but swap in our rotating codec.
        data_converter=dataclasses.replace(
            temporalio.converter.default(),
            payload_codec=RotatingEncryptionCodec(keyring, active_key_id),
        ),
    )
