"""Demonstrates encryption key rotation end to end.

Run the worker first (`just worker`), then this (`just start`). It:

  1. Starts a workflow while the active key is `key-2024`.
  2. Rotates: new clients start encrypting with `key-2025`, keeping `key-2024`
     in the keyring.
  3. Reads the workflow's result with the full keyring -- a single workflow
     whose history mixes both keys decodes cleanly.
  4. Shows the failure mode: a reader that DROPPED the retired `key-2024`
     cannot read data that key wrote.
"""

import asyncio
import uuid

from temporalio.api.common.v1 import Payload

from app.codec import ENCODING, RotatingEncryptionCodec
from app.keyring import KEYRING, TASK_QUEUE, connect
from app.workflows import SecretVaultWorkflow


def banner(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


async def main() -> None:
    wf_id = f"secret-vault-{uuid.uuid4()}"

    banner("1. Start a workflow while the ACTIVE key is 'key-2024'")
    old_client = await connect("key-2024")
    handle = await old_client.start_workflow(
        SecretVaultWorkflow.run,
        "alpha",
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"Started {wf_id}")
    print("  -> input 'alpha' encrypted with key-2024")
    await handle.signal(SecretVaultWorkflow.add_secret, "beta")
    print("  -> signalled 'beta' encrypted with key-2024")

    banner("2. ROTATE: new clients now encrypt with 'key-2025'")
    print("key-2024 STAYS in the keyring, so payloads it wrote remain readable.")
    new_client = await connect("key-2025")
    new_handle = new_client.get_workflow_handle(wf_id)
    await new_handle.signal(SecretVaultWorkflow.add_secret, "gamma")
    print("  -> signalled 'gamma' encrypted with key-2025")
    await new_handle.signal(SecretVaultWorkflow.finish)

    banner("3. Read the result with the FULL keyring (key-2024 + key-2025)")
    secrets = await new_handle.result()
    print(f"Secrets from a workflow that outlived a rotation: {secrets}")
    print("Its history holds payloads encrypted under BOTH keys -- all decodable.")

    banner("4. Failure mode: what if you DROP the retired key-2024?")
    # Represent some data written last year with key-2024.
    key2024_codec = RotatingEncryptionCodec(KEYRING, "key-2024")
    [at_rest] = await key2024_codec.encode(
        [Payload(metadata={"encoding": b"json/plain"}, data=b'"last-year-secret"')]
    )
    print(f"Data was written with key ID: "
          f"{at_rest.metadata['encryption-key-id'].decode()}")

    # A reader that kept only key-2025 cannot read it.
    dropped_old = RotatingEncryptionCodec({"key-2025": KEYRING["key-2025"]}, "key-2025")
    try:
        await dropped_old.decode([at_rest])
        print("  UNEXPECTED: decode succeeded")
    except ValueError as e:
        print(f"  key-2025-only reader FAILS (as expected): {e}")

    # The full keyring still reads it.
    full = RotatingEncryptionCodec(KEYRING, "key-2025")
    [recovered] = await full.decode([at_rest])
    print(f"  full-keyring reader recovers it: {recovered.data.decode()}")

    banner("Takeaway")
    print("Rotate = add a new active key. Keep old keys to read old data.")


if __name__ == "__main__":
    asyncio.run(main())
