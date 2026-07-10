import logging

from temporalio.client import Client, Plugin
from temporalio.envconfig import ClientConfig


async def connect(identity: str, *, plugins: list[Plugin] | None = None) -> Client:
    """Connect to the local dev server (localhost:7233) using the same
    envconfig pattern as the other projects in this playground.

    ``plugins`` lets callers pass Temporal client plugins — here we use
    pydantic-ai's ``PydanticAIPlugin`` so the client (and any worker created
    from it) gets pydantic serialization + the pydantic-ai workflow sandbox.
    """
    config = ClientConfig.load_client_connect_config()
    config.setdefault("target_host", "localhost:7233")
    return await Client.connect(**config, identity=identity, plugins=plugins or [])


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
