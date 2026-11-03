"""Download a remote file without letting the URL reach internal addresses.

Every server-side download goes through here rather than calling httpx directly.
A URL that looks external can still resolve to 127.0.0.1, the droplet metadata
service at 169.254.169.254, or a private VPC address, and a plain httpx.get
would happily fetch it and hand the bytes back to whoever supplied the URL.

The checks run after DNS resolution and again on every redirect hop, since a
public host can redirect to an internal one. Responses are size-capped while
streaming, so a hostile or broken origin cannot exhaust a worker's memory.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50MB, comfortably above any generated image
DEFAULT_TIMEOUT = 60.0
MAX_REDIRECTS = 3


class UnsafeURLError(ValueError):
    """The URL is not one the server is allowed to fetch."""


class HostLookupFailed(UnsafeURLError):
    """The host did not resolve, so nothing is known about it yet. Worth retrying."""


def _parse(url: str, schemes: tuple[str, ...]) -> tuple[str, int]:
    parsed = urlparse(url or "")
    if parsed.scheme not in schemes:
        raise UnsafeURLError(f"URL scheme '{parsed.scheme}' not allowed")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


def _check_addresses(host: str, infos) -> None:
    if not infos:
        raise HostLookupFailed(f"Host '{host}' did not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        # is_global excludes loopback, private, link-local (metadata),
        # carrier-grade NAT, unique-local IPv6 and the reserved ranges.
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURLError(f"Host '{host}' resolves to a non-public address")


def _validate(url: str, schemes: tuple[str, ...]) -> None:
    host, port = _parse(url, schemes)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HostLookupFailed(f"Host '{host}' did not resolve") from exc
    _check_addresses(host, infos)


async def _avalidate(url: str, schemes: tuple[str, ...]) -> None:
    host, port = _parse(url, schemes)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HostLookupFailed(f"Host '{host}' did not resolve") from exc
    _check_addresses(host, infos)


def _check_length(response: httpx.Response, max_bytes: int) -> None:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise UnsafeURLError(f"Response is larger than {max_bytes} bytes")


def fetch_bytes(
    url: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
    schemes: tuple[str, ...] = ("https",),
) -> bytes:
    """GET a URL and return the body. Raises UnsafeURLError or httpx errors."""
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _validate(url, schemes)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                _check_length(response, max_bytes)
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise UnsafeURLError(f"Response is larger than {max_bytes} bytes")
                return bytes(body)
    raise UnsafeURLError("Too many redirects")


async def afetch_bytes(
    url: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
    schemes: tuple[str, ...] = ("https",),
) -> bytes:
    """Async form of fetch_bytes."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _avalidate(url, schemes)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                _check_length(response, max_bytes)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise UnsafeURLError(f"Response is larger than {max_bytes} bytes")
                return bytes(body)
    raise UnsafeURLError("Too many redirects")
