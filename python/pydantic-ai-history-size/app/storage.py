"""External storage (the "claim-check" pattern) for large payloads.

Temporal's external-storage feature (Public Preview in ``temporalio`` 1.27)
intercepts payloads on the data-converter I/O path: any payload larger than a
threshold is handed to a ``StorageDriver`` which persists it externally and
returns a small *claim* (a reference). Only that claim is written to Temporal
event history, so history stores pointers instead of the fat bytes; on the way
back the driver retrieves the payload from the claim. This runs *outside* the
workflow (during payload encode/decode), so there are no determinism concerns.

``LocalDiskStorageDriver`` is a minimal local-filesystem driver (adapted from the
Temporal features repo). In production, point a driver at S3/GCS/blob storage
(``temporalio.contrib.aws.s3driver`` ships an S3 one) and plan for lifecycle/GC
of stored objects.

See: https://github.com/temporalio/features/blob/main/features/snippets/external_storage/custom_driver/custom_storage_driver.py
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from collections.abc import Sequence

from temporalio.api.common.v1 import Payload
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.converter import (
    DataConverter,
    ExternalStorage,
    StorageDriver,
    StorageDriverClaim,
    StorageDriverRetrieveContext,
    StorageDriverStoreContext,
)

from app.constants import EXTERNAL_STORAGE_DIR, EXTERNAL_STORAGE_THRESHOLD_KB


class LocalDiskStorageDriver(StorageDriver):
    """Persists over-threshold payloads to local files; the claim is the path."""

    def __init__(self, store_dir: str = EXTERNAL_STORAGE_DIR) -> None:
        self._store_dir = os.path.abspath(store_dir)

    def name(self) -> str:
        return "local-disk"

    async def store(
        self,
        context: StorageDriverStoreContext,
        payloads: Sequence[Payload],
    ) -> list[StorageDriverClaim]:
        # Group objects by namespace/workflow-or-activity id when available.
        prefix = self._store_dir
        target = context.target
        namespace = getattr(target, "namespace", None)
        target_id = getattr(target, "id", None)
        if namespace and target_id:
            prefix = os.path.join(self._store_dir, namespace, target_id)
        os.makedirs(prefix, exist_ok=True)

        claims: list[StorageDriverClaim] = []
        for payload in payloads:
            file_path = os.path.join(prefix, f"{uuid.uuid4()}.bin")
            with open(file_path, "wb") as f:
                f.write(payload.SerializeToString())
            claims.append(StorageDriverClaim(claim_data={"path": file_path}))
        return claims

    async def retrieve(
        self,
        context: StorageDriverRetrieveContext,
        claims: Sequence[StorageDriverClaim],
    ) -> list[Payload]:
        payloads: list[Payload] = []
        for claim in claims:
            with open(claim.claim_data["path"], "rb") as f:
                payload = Payload()
                payload.ParseFromString(f.read())
                payloads.append(payload)
        return payloads


def build_data_converter() -> DataConverter:
    """The pydantic converter + external storage.

    ``PydanticAIPlugin`` keeps a supplied converter as-is when its
    ``payload_converter_class`` is a ``PydanticPayloadConverter`` (it is here),
    so this drops straight in alongside the plugin.
    """
    return dataclasses.replace(
        pydantic_data_converter,
        external_storage=ExternalStorage(
            drivers=[LocalDiskStorageDriver()],
            payload_size_threshold=EXTERNAL_STORAGE_THRESHOLD_KB * 1024,
        ),
    )
