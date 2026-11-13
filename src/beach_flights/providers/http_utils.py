"""HTTP client helper resilient to bare IPv6 tokens in NO_PROXY and custom CA bundles."""

from __future__ import annotations

import os
import ssl
from pathlib import Path

import httpx


def _resolve_verify() -> ssl.SSLContext | bool:
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and Path(path).exists():
            return ssl.create_default_context(cafile=path)
    return True


def create_http_client(timeout_seconds: float = 15.0) -> httpx.Client:
    """Create an httpx.Client honoring environment proxies and CA bundles."""
    verify = _resolve_verify()
    try:
        return httpx.Client(timeout=timeout_seconds, verify=verify)
    except httpx.InvalidURL:
        proxy = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
        )
        return httpx.Client(
            timeout=timeout_seconds,
            proxy=proxy,
            verify=verify,
            trust_env=False,
        )
