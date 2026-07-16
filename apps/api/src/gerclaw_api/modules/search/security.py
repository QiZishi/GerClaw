"""Privacy and SSRF controls applied before online search provider calls."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from gerclaw_api.modules.privacy_redaction.policy import redact_external_search_query


class UnsafeSearchURLError(ValueError):
    """Raised before a provider receives a non-public extraction target."""


def sanitize_search_query(query: str) -> str:
    """Compatibility projection for the shared external-search privacy policy."""

    return redact_external_search_query(query).text


Resolver = Callable[[str, int], Awaitable[list[str]]]


@dataclass(frozen=True, slots=True)
class _ValidatedTarget:
    url: str
    hostname: str
    addresses: tuple[str, ...]


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
        target = await self._validate_target(url)
        if not self._probe_redirects:
            return target.url
        for _redirect_index in range(5):
            status_code, location = await self._probe_get(target)
            if status_code not in {301, 302, 303, 307, 308}:
                return target.url
            if not location:
                raise UnsafeSearchURLError("extraction redirect omitted its target")
            target = await self._validate_target(urljoin(target.url, location))
        raise UnsafeSearchURLError("extraction URL exceeded the redirect limit")

    async def _probe_get(self, target: _ValidatedTarget) -> tuple[int, str | None]:
        """Probe with GET while pinning production TLS to a validated public IP."""

        if self._redirect_transport is not None:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(5.0),
                transport=self._redirect_transport,
            ) as client:
                try:
                    async with client.stream(
                        "GET",
                        target.url,
                        headers={"Accept-Encoding": "identity", "Range": "bytes=0-0"},
                    ) as response:
                        return response.status_code, response.headers.get("location")
                except httpx.RequestError as error:
                    raise UnsafeSearchURLError("extraction redirect safety probe failed") from error

        last_error: BaseException | None = None
        for address in target.addresses:
            try:
                return await asyncio.wait_for(self._pinned_tls_get(target, address), timeout=5.0)
            except (OSError, TimeoutError, ssl.SSLError, asyncio.IncompleteReadError) as error:
                last_error = error
        raise UnsafeSearchURLError("extraction redirect safety probe failed") from last_error

    @staticmethod
    async def _pinned_tls_get(target: _ValidatedTarget, address: str) -> tuple[int, str | None]:
        """Connect to the validated IP while authenticating TLS for the original host."""

        reader, writer = await asyncio.open_connection(
            address,
            443,
            ssl=ssl.create_default_context(),
            server_hostname=target.hostname,
            limit=65_536,
        )
        try:
            parsed = urlsplit(target.url)
            request_target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            request = (
                f"GET {request_target} HTTP/1.1\r\n"
                f"Host: {target.hostname}\r\n"
                "User-Agent: GerClaw-URL-Safety-Probe/1.0\r\n"
                "Accept: */*\r\n"
                "Accept-Encoding: identity\r\n"
                "Range: bytes=0-0\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(request.encode("ascii"))
            await writer.drain()
            header_block = await reader.readuntil(b"\r\n\r\n")
            if len(header_block) > 65_536:
                raise UnsafeSearchURLError("extraction response headers exceeded the limit")
            try:
                lines = header_block.decode("iso-8859-1").split("\r\n")
                status_code = int(lines[0].split(" ", 2)[1])
            except (IndexError, ValueError) as error:
                raise UnsafeSearchURLError(
                    "extraction probe returned an invalid response"
                ) from error
            location = None
            for line in lines[1:]:
                if line.casefold().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
                    break
            return status_code, location
        finally:
            writer.close()
            await writer.wait_closed()

    async def _validate_target(self, url: str) -> _ValidatedTarget:
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
            addresses = [str(direct_address)]

        netloc = ascii_hostname
        if ":" in ascii_hostname:
            netloc = f"[{ascii_hostname}]"
        canonical = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
        return _ValidatedTarget(
            url=canonical,
            hostname=ascii_hostname,
            addresses=tuple(sorted(set(addresses))),
        )
