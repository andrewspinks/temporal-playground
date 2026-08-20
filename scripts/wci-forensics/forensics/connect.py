"""Temporal client connection (API key or mTLS, optional HTTP-connect proxy)."""
from __future__ import annotations

import dataclasses
from typing import Optional

from temporalio.client import Client
from temporalio.service import HttpConnectProxyConfig, TLSConfig


@dataclasses.dataclass
class ConnOptions:
    address: str
    namespace: str
    api_key: Optional[str] = None
    tls: bool = False
    no_tls: bool = False  # force plaintext (e.g. a local proxy), overriding api-key auto-TLS
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None
    tls_ca: Optional[str] = None
    tls_server_name: Optional[str] = None
    proxy: Optional[str] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


async def connect(o: ConnOptions) -> Client:
    tls_config = None
    if o.tls_cert or o.tls_key or o.tls_ca or o.tls_server_name:
        tls_config = TLSConfig(
            client_cert=_read(o.tls_cert) if o.tls_cert else None,
            client_private_key=_read(o.tls_key) if o.tls_key else None,
            server_root_ca_cert=_read(o.tls_ca) if o.tls_ca else None,
            domain=o.tls_server_name,
        )

    # api_key implies TLS on Temporal Cloud; enable it unless mTLS is already set.
    # --no-tls forces plaintext (e.g. a local gRPC proxy that terminates TLS itself).
    if o.no_tls:
        tls_arg = False
    else:
        tls_arg = tls_config if tls_config is not None else (True if (o.tls or o.api_key) else False)

    proxy = None
    if o.proxy:
        basic = (o.proxy_user, o.proxy_pass) if o.proxy_user is not None else None
        proxy = HttpConnectProxyConfig(target_host=o.proxy, basic_auth=basic)

    return await Client.connect(
        o.address,
        namespace=o.namespace,
        api_key=o.api_key,
        tls=tls_arg,
        http_connect_proxy_config=proxy,
    )
