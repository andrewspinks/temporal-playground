"""An AES-GCM payload codec that supports encryption key ROTATION.

The whole trick to rotation lives in two rules:

1.  On ENCRYPT we always use the current *active* key, and we stamp that
    key's ID into the payload metadata (`encryption-key-id`).
2.  On DECRYPT we look the key up *by the ID stamped on that payload* -- not
    by the active key.

Because every payload remembers which key wrote it, a payload encrypted with
last year's key stays decryptable after you rotate to a new active key -- as
long as you keep the old key in the keyring. Rotating is therefore just
"start encrypting with a new key, but keep the old ones around to read".

Compare this with the stock `temporalio` encryption sample, whose `decode`
raises `ValueError` unless the payload's key ID equals the single configured
key -- that codec deliberately does NOT support rotation.
"""

import os
from typing import Dict, Iterable, List

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec

ENCODING = b"binary/encrypted"


class RotatingEncryptionCodec(PayloadCodec):
    """Encrypts with the active key; decrypts with whichever key wrote each payload.

    Args:
        keyring: every key this codec can decrypt with, keyed by key ID. Keys
            must be 16, 24, or 32 bytes (AES-128/192/256).
        active_key_id: the key ID used to encrypt new payloads. Must be present
            in ``keyring``.
    """

    def __init__(self, keyring: Dict[str, bytes], active_key_id: str) -> None:
        super().__init__()
        if active_key_id not in keyring:
            raise ValueError(
                f"Active key ID {active_key_id!r} is not in the keyring "
                f"{sorted(keyring)}."
            )
        self.keyring = dict(keyring)
        self.active_key_id = active_key_id

    def _cipher(self, key_id: str) -> AESGCM:
        key = self.keyring.get(key_id)
        if key is None:
            # In production this is where you would call your KMS / secrets
            # manager to fetch a key you do not have cached, then add it to the
            # keyring. Here we fail loudly so the "dropped an old key" scenario
            # is obvious.
            raise ValueError(
                f"Unknown key ID {key_id!r}. Known key IDs: {sorted(self.keyring)}. "
                "This payload was encrypted with a key that is not in the keyring "
                "-- if it is a retired key, add it back to decode this data."
            )
        return AESGCM(key)

    async def encode(self, payloads: Iterable[Payload]) -> List[Payload]:
        # Always encrypt with the current active key, stamping its ID so a
        # future decode knows which key to reach for.
        return [
            Payload(
                metadata={
                    "encoding": ENCODING,
                    "encryption-key-id": self.active_key_id.encode(),
                },
                data=self._encrypt(self.active_key_id, p.SerializeToString()),
            )
            for p in payloads
        ]

    async def decode(self, payloads: Iterable[Payload]) -> List[Payload]:
        ret: List[Payload] = []
        for p in payloads:
            # Leave anything we did not encrypt untouched.
            if p.metadata.get("encoding", b"") != ENCODING:
                ret.append(p)
                continue
            # Decrypt with the key that ENCRYPTED this payload, which may be an
            # older key than the active one. This is what makes rotation safe.
            key_id = p.metadata.get("encryption-key-id", b"").decode()
            ret.append(Payload.FromString(self._decrypt(key_id, p.data)))
        return ret

    def _encrypt(self, key_id: str, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._cipher(key_id).encrypt(nonce, data, None)

    def _decrypt(self, key_id: str, data: bytes) -> bytes:
        return self._cipher(key_id).decrypt(data[:12], data[12:], None)
