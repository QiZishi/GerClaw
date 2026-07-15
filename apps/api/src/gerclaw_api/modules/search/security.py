"""Privacy and SSRF controls applied before online search provider calls."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from typing import cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from gerclaw_api.security import redact_text

_NAME_PATTERNS = (
    re.compile(
        r"(?:我叫|姓名(?:是|为|[:：])?|患者(?:姓名)?(?:是|为|[:：])?)\s*[\u4e00-\u9fff]{2,4}"
    ),
    re.compile(r"(?:name\s*[:=]\s*)[A-Za-z][A-Za-z .'-]{1,80}", re.IGNORECASE),
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class UnsafeSearchURLError(ValueError):
    """Raised before a provider receives a non-public extraction target."""


def sanitize_search_query(query: str) -> str:
    """Remove common direct identifiers while preserving clinical search intent."""

    sanitized = redact_text(_CONTROL.sub(" ", query))
    for pattern in _NAME_PATTERNS:
        sanitized = pattern.sub("患者", sanitized)
    normalized = " ".join(sanitized.split()).strip()
    if not normalized:
        raise ValueError("search query cannot be blank after privacy filtering")
    return normalized


Resolver = Callable[[str, int], Awaitable[list[str]]]


async def _system_resolver(hostname: str, port: int) -> list[str]:
    def resolve() -> list[str]:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        return list({cast(str, record[4][0]).split("%", 1)[0] for record in records})

    return await asyncio.to_thread(resolve)


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global and not address.is_multicast and not address.is_unspecified)


class PublicURLGuard:
    """Resolve and allow only credential-free public HTTPS extraction URLs."""

    def __init__(
        self,
        resolver: Resolver | None = None,
        *,
        probe_redirects: bool | None = None,
        redirect_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._resolver = resolver or _system_resolver
        self._probe_redirects = resolver is None if probe_redirects is None else probe_redirects
        self._redirect_transport = redirect_transport

    async def validate(self, url: str) -> str:
        canonical = await self._validate_target(url)
        if not self._probe_redirects:
            return canonical
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(5.0),
            transport=self._redirect_transport,
        ) as client:
            for _redirect_index in range(5):
                try:
                    response = await client.head(canonical)
                except httpx.RequestError as error:
                    raise UnsafeSearchURLError("extraction redirect safety probe failed") from error
                if response.status_code not in {301, 302, 303, 307, 308}:
                    return canonical
                location = response.headers.get("location")
                if not location:
                    raise UnsafeSearchURLError("extraction redirect omitted its target")
                canonical = await self._validate_target(urljoin(canonical, location))
        raise UnsafeSearchURLError("extraction URL exceeded the redirect limit")

    async def _validate_target(self, url: str) -> str:
        if len(url) > 2_048:
            raise UnsafeSearchURLError("extraction URL exceeds the length limit")
        parsed = urlsplit(url.strip())
        if parsed.scheme.casefold() != "https":
            raise UnsafeSearchURLError("only HTTPS extraction URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeSearchURLError("URL credentials are not allowed")
        hostname = parsed.hostname
        if not hostname:
            raise UnsafeSearchURLError("extraction URL has no hostname")
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError as error:
            raise UnsafeSearchURLError("extraction hostname is invalid") from error
        if ascii_hostname == "localhost" or ascii_hostname.endswith(".localhost"):
            raise UnsafeSearchURLError("local extraction targets are forbidden")
        try:
            port = parsed.port
        except ValueError as error:
            raise UnsafeSearchURLError("extraction URL port is invalid") from error
        if port not in (None, 443):
            raise UnsafeSearchURLError("non-standard extraction ports are forbidden")

        try:
            direct_address = ipaddress.ip_address(ascii_hostname)
        except ValueError:
            try:
                addresses = await self._resolver(ascii_hostname, 443)
            except (OSError, TimeoutError) as error:
                raise UnsafeSearchURLError("extraction hostname could not be resolved") from error
            if not addresses or any(not _is_public_address(item) for item in addresses):
                raise UnsafeSearchURLError(
                    "extraction hostname resolved outside the public internet"
                ) from None
        else:
            if not _is_public_address(str(direct_address)):
                raise UnsafeSearchURLError("private extraction targets are forbidden")

        netloc = ascii_hostname
        if ":" in ascii_hostname:
            netloc = f"[{ascii_hostname}]"
        canonical = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
        return canonical
