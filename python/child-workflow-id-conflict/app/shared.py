import logging

from temporalio.client import Client
from temporalio.envconfig import ClientConfig


async def connect(identity: str) -> Client:
    """Connect to the local dev server (localhost:7233) using the same
    envconfig pattern as the other projects in this playground."""
    config = ClientConfig.load_client_connect_config()
    config.setdefault("target_host", "localhost:7233")
    return await Client.connect(**config, identity=identity)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
