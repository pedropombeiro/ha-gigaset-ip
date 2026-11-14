"""Private, serialized web sessions for legacy Gigaset IP bases.

Only the English web interface is currently supported. No JavaScript is executed.
Raw pages and credentials must never be logged or exported in diagnostics.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import aiohttp

STATUS_PAGE = "status_connections.html"
REBOOT_PAGE = "settings_management_reboot_and_reset.html"


class GigasetError(Exception):
    """The base could not be queried safely."""


class InvalidAuth(GigasetError):
    """The base explicitly rejected the system PIN."""


class SessionBusy(GigasetError):
    """Another client owns the web session."""


class ParseError(GigasetError):
    """The response is not a supported status page."""


@dataclass(frozen=True)
class Connection:
    """One connection, identified by its base slot rather than its display name."""

    slot: str
    name: str
    status: str
    kind: str

    @property
    def registered(self) -> bool | None:
        """Return None for states with no proven registration result."""
        if self.status == "Registered":
            return True
        if self.status in {
            "Registration failed.",
            "Registration failed",
            "Disconnected",
        }:
            return False
        return None

    @property
    def enabled_by_default(self) -> bool:
        """Exclude disabled accounts and the fixed line by default."""
        return self.kind != "Fixed line" and self.status != "Disabled"


@dataclass(frozen=True)
class Device:
    """Public device metadata without account identifiers."""

    mac: str
    model: str
    firmware: str | None


class Rows(HTMLParser):
    """Collect leaf table rows, preserving nested cell text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._stack: list[list[str]] = []
        self._cell: list[str] | None = None
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._ignored += 1
        if tag == "tr":
            self._stack.append([])
        if tag == "td":
            self._cell = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._ignored = max(0, self._ignored - 1)
        if tag == "td" and self._cell is not None and self._stack:
            self._stack[-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        if tag == "tr" and self._stack:
            self.rows.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None and not self._ignored:
            self._cell.append(data)


def parse_connections(
    html: str, device_html: str | None = None
) -> dict[str, Connection]:
    """Parse English status rows. Never turn unexpected HTML into an outage."""
    parser = Rows()
    parser.feed(html)
    connections = {}
    voip_slot = 0
    slots = parse_slots(device_html) if device_html is not None else None
    for row in parser.rows:
        if len(row) != 4 or row[0] not in {"VoIP", "Gigaset.net", "Fixed line"}:
            continue
        kind, name, status, _ = row
        if not name or not status:
            raise ParseError("Incomplete connection row")
        if kind == "VoIP":
            voip_slot += 1
            if slots is not None and name not in slots:
                raise ParseError("Connection has no unambiguous hardware slot")
            slot = f"voip_{slots[name] if slots is not None else voip_slot}"
        else:
            slot = "gigaset_net" if kind == "Gigaset.net" else "fixed_line"
        if slot in connections:
            raise ParseError("Duplicate connection slot")
        connections[slot] = Connection(slot, name, status, kind)
    if not connections:
        raise ParseError("No supported connection rows")
    return connections


def parse_slots(html: str) -> dict[str, int]:
    """Read firmware slot metadata without executing JavaScript.

    Display rows omit unused accounts. The device page retains the six VoIP
    slots and their numeric IDs in lines[index][6]. Reject ambiguous labels
    rather than silently attaching one account's state to another entity.
    """
    names = re.findall(r"lines\[(\d+)\]\[0\]\s*=\s*'((?:\\.|[^'\\])*)'\s*;", html)
    ids = dict(re.findall(r"lines\[(\d+)\]\[6\]\s*=\s*(\d+)\s*;", html))
    slots = {}
    seen = set()
    for index, name in names:
        if index not in ids:
            raise ParseError("Incomplete slot metadata")
        slot = int(ids[index])
        if slot > 5:
            continue
        if re.search(r"\\(?!['\\])", name):
            raise ParseError("Unsupported escaped account label")
        name = re.sub(r"\\(['\\])", r"\1", name)
        if name in slots or slot in seen:
            raise ParseError("Ambiguous slot metadata")
        slots[name] = slot + 1
        seen.add(slot)
    if not slots:
        raise ParseError("Missing slot metadata")
    return slots


def parse_device(html: str) -> Device:
    """Extract the MAC from the labeled row, not another identifier in scripts."""
    parser = Rows()
    parser.feed(html)
    mac = next(
        (r[1] for r in parser.rows if len(r) == 2 and r[0] == "MAC address:"), ""
    )
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
        raise ParseError("Missing device MAC address")
    model = re.search(r"<title>\s*([^<]+?)\s*</title>", html, re.I)
    firmware = re.search(r"var\s+FirmVer\s*=\s*(\d+)", html)
    return Device(
        mac.lower(),
        model[1] if model else "Gigaset IP",
        firmware[1] if firmware else None,
    )


def login_error(html: str) -> None:
    """Use the firmware's error code instead of localized error strings."""
    match = re.search(r"var\s+error\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;", html)
    if not match:
        return
    code = int(match[1], 16 if match[1].lower().startswith("0x") else 10)
    if code == 1:
        raise InvalidAuth("System PIN rejected")
    if code == 2:
        raise SessionBusy("Web session already in use")
    if code:
        raise GigasetError("Base temporarily unavailable")


def normalize_host(host: str) -> str:
    """Allow one local HTTP(S) origin without embedded credentials or paths."""
    parsed = urlsplit(host if "://" in host else f"http://{host}")
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Enter a hostname or HTTP(S) origin")
    # Accessing port also validates its syntax.
    _ = parsed.port
    return f"{parsed.scheme}://{parsed.netloc}/"


class GigasetClient:
    """Keep the PIN out of URLs and use a separate cookie jar for each login."""

    def __init__(self, host: str, pin: str):
        self.base_url = normalize_host(host)
        self._pin = pin
        self._lock = asyncio.Lock()

    async def _request(self, session, page, data=None):
        url = urljoin(self.base_url, page)
        # Redirects are handled explicitly so a PIN POST can never be replayed.
        for _ in range(5):
            async with session.request(
                "POST" if data is not None else "GET",
                url,
                data=data,
                allow_redirects=False,
            ) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    target = urljoin(url, response.headers.get("Location", ""))
                    if (
                        urlsplit(target).netloc != urlsplit(self.base_url).netloc
                        or urlsplit(target).scheme != urlsplit(self.base_url).scheme
                        or response.status in {307, 308}
                    ):
                        raise GigasetError("Unsafe redirect rejected")
                    url, data = target, None
                    continue
                if response.status != 200:
                    raise GigasetError("Unexpected HTTP status")
                return await response.text(errors="replace")
        raise GigasetError("Too many redirects")

    @asynccontextmanager
    async def _authenticated(self):
        async with self._lock:
            async with aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as session:
                logged_in = False
                try:
                    page = await self._request(session, "login.html")
                    login_error(page)
                    page = await self._request(
                        session,
                        "login.html",
                        {
                            "password": self._pin,
                            "language": "1",
                        },
                    )
                    login_error(page)
                    # An authenticated page always has a logout link. Do not log
                    # out a different user's session when authentication failed.
                    logged_in = bool(re.search(r"href=[\'\"]/?logout\.html", page))
                    status = await self._request(session, STATUS_PAGE)
                    login_error(status)
                    if re.search(r"name=[\'\"]password[\'\"]", status):
                        raise GigasetError("Login did not establish a session")
                    logged_in = True
                    yield session, status
                finally:
                    if logged_in:
                        try:
                            await self._request(session, "logout.html")
                        except GigasetError, aiohttp.ClientError, TimeoutError:
                            pass

    async def async_update(self, *, include_device=False):
        """Read registration and optionally device identity in a short session."""
        try:
            async with self._authenticated() as (session, page):
                device_html = await self._request(session, "status_device.html")
                connections = parse_connections(page, device_html)
                device = None
                if include_device:
                    device = parse_device(device_html)
                return connections, device
        except (aiohttp.ClientError, TimeoutError) as error:
            raise GigasetError("Cannot communicate with base") from error

    async def async_reboot(self):
        """Submit only the reboot operation (1), never the factory reset (2)."""
        try:
            async with self._authenticated() as (session, _):
                page = await self._request(session, REBOOT_PAGE)
                if not re.search(r"name=[\'\"]reboot_reset_function[\'\"]", page):
                    raise ParseError("Unsupported reboot form")
                data = aiohttp.FormData()
                data.add_field("reboot_reset_function", "1", content_type="text/plain")
                # Never retry: a disconnected response may mean reboot succeeded.
                await self._request(session, REBOOT_PAGE, data)
        except (aiohttp.ClientError, TimeoutError) as error:
            raise GigasetError(
                "Reboot response unconfirmed; check base before retrying"
            ) from error
