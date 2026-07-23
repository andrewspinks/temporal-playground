# Encryption Key Rotation (Python)

A Temporal payload-encryption sample that demonstrates **rotating encryption
keys** — swapping the key you encrypt with while keeping old workflows and old
history readable.

## The idea

A `PayloadCodec` encrypts every payload (workflow inputs, activity args/results,
signals, queries, results) before it leaves your process and decrypts it on the
way back in. Rotation works because of two rules in
[`app/codec.py`](app/codec.py):

1. **Encrypt** with the current *active* key, and stamp that key's ID into the
   payload metadata (`encryption-key-id`).
2. **Decrypt** with the key named by *that stamp*, not the active key.

Every payload remembers which key wrote it, so data encrypted with a retired key
stays readable — **as long as you keep the old key in the keyring**. To rotate,
you add a new key and make it active; you never delete old keys.

> Contrast with the stock `temporalio` encryption sample, whose `decode` raises
> `ValueError` unless the payload's key ID equals the single configured key — it
> deliberately does *not* support rotation.

## Files

| File | Role |
| --- | --- |
| [`app/codec.py`](app/codec.py) | `RotatingEncryptionCodec` — AES-GCM, keyring keyed by key ID, per-payload key lookup |
| [`app/keyring.py`](app/keyring.py) | In-memory "KMS": the full keyring + `connect()` helper that builds a client with a chosen active key |
| [`app/workflows.py`](app/workflows.py) | `SecretVaultWorkflow` — collects secrets via signals, designed to outlive a rotation |
| [`app/activities.py`](app/activities.py) | `store_secret` — shows activity payloads are encrypted too |
| [`app/worker.py`](app/worker.py) | Worker with the full keyring, encrypting with the newest key |
| [`app/starter.py`](app/starter.py) | The end-to-end rotation demonstration |

## Run it

From the playground root, start the dev server:

```sh
just server
```

Then, in `python/encryption-key-rotation/`:

```sh
just worker      # terminal 1 — holds the full keyring
just start       # terminal 2 — runs the rotation demo
```

`just start` walks through:

1. Start a workflow while the active key is `key-2024` (input + a signal
   encrypted with `key-2024`).
2. **Rotate** — new clients encrypt with `key-2025`, keeping `key-2024` in the
   keyring; send another signal.
3. Read the result with the full keyring: a single workflow whose history mixes
   both keys decodes cleanly.
4. Show the failure mode — a reader that dropped `key-2024` cannot read data
   that key wrote, while the full-keyring reader still can.

## Adapting it

- **Real key management**: replace the `KEYRING` dict in `app/keyring.py` with
  lookups against AWS KMS / GCP KMS / Vault. The natural extension point is
  `RotatingEncryptionCodec._cipher` — fetch and cache a key you don't have when
  a payload references an unknown key ID.
- **Rotating the worker**: this sample keeps the worker on the newest key. In a
  real rollout you'd redeploy workers with the new key added to the keyring
  first (so they can *decrypt* it), then flip the active key.
- **Web UI / CLI decoding**: to view encrypted payloads in the Web UI or `temporal`
  CLI, run a [codec server](https://docs.temporal.io/production-deployment/data-encryption)
  that exposes the same keyring.

## Cloud

Connection switching is handled by `temporalio.envconfig.ClientConfig` — set
`TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, and either mTLS certs
(`TEMPORAL_TLS_CLIENT_CERT` / `TEMPORAL_TLS_CLIENT_KEY`) or `TEMPORAL_API_KEY`.
No code changes needed.
