import logging

from temporalio.client import Client, Plugin
from temporalio.converter import DataConverter
from temporalio.envconfig import ClientConfig


async def connect(
    identity: str,
    *,
    plugins: list[Plugin] | None = None,
    data_converter: DataConverter | None = None,
) -> Client:
    """Connect to the local dev server (localhost:7233) using the same
    envconfig pattern as the other projects in this playground.

    ``plugins`` lets callers pass Temporal client plugins — here we use
    pydantic-ai's ``PydanticAIPlugin`` so the client (and any worker created
    from it) gets pydantic serialization + the pydantic-ai workflow sandbox.
    ``data_converter`` overrides serialization — here the pydantic converter
    plus external storage (see app/storage.py).
    """
    config = ClientConfig.load_client_connect_config()
    config.setdefault("target_host", "localhost:7233")
    kwargs = dict(config, identity=identity, plugins=plugins or [])
    if data_converter is not None:
        kwargs["data_converter"] = data_converter
    return await Client.connect(**kwargs)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
