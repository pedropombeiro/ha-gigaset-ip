"""Test status parsing and safe, short-lived sessions."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from aioresponses import aioresponses


def test_connections(client_api, status_html):
    connections = client_api.parse_connections(status_html)
    assert len(connections) == 5
    assert connections["voip_1"].registered is True
    assert connections["voip_2"].registered is False
    assert connections["voip_3"].registered is None
    assert not connections["voip_3"].enabled_by_default
    assert not connections["fixed_line"].enabled_by_default
    assert connections["gigaset_net"].registered is True


def test_unrecognized_status(client_api, status_html):
    connections = client_api.parse_connections(
        status_html.replace("Registered", "Trying")
    )
    assert connections["voip_1"].registered is None


@pytest.mark.parametrize(
    "html", ["", "<html>Login</html>", "<table><tr><td>VoIP</td></tr></table>"]
)
def test_invalid_pages(client_api, html):
    with pytest.raises(client_api.ParseError):
        client_api.parse_connections(html)


def test_device_identity(client_api):
    html = (
        "<title>Example base</title><table><tr><td>MAC address:</td>"
        "<td>02:00:00:00:00:01</td></tr></table><script>var FirmVer = 123456;</script>"
    )
    device = client_api.parse_device(html)
    assert device.mac == "02:00:00:00:00:01"
    assert device.firmware == "123456"
    with pytest.raises(client_api.ParseError):
        client_api.parse_device("<title>Login</title>")


def test_base_diagnostics(client_api, device_html):
    device = client_api.parse_device(device_html)
    assert device.firmware == "42.263"
    assert device.last_ntp_sync.value == datetime(2026, 1, 10, 1, 50)
    assert device.boot_time.value == datetime(2026, 1, 9, 10, 11)
    assert device.last_ntp_sync.status == "ok"


@pytest.mark.parametrize(
    "value,status",
    [
        ("Never", "never"),
        ("", "invalid"),
        ("31.02.2026 01:50", "invalid"),
        ("unrecognized", "invalid"),
        ("01/10/2026 01:50", "invalid"),
    ],
)
def test_optional_timestamp_states(client_api, device_html, value, status):
    device = client_api.parse_device(device_html.replace("10.01.2026 01:50", value))
    assert device.last_ntp_sync.value is None
    assert device.last_ntp_sync.status == status
    assert device.boot_time.status == "ok"


def test_missing_and_duplicate_timestamp(client_api):
    assert (
        client_api.parse_timestamp([], "Last synchronization:").status == "not_reported"
    )
    row = ["Last synchronization:", "10.01.2026 01:50"]
    assert client_api.parse_timestamp([row, row], row[0]).status == "invalid"


@pytest.mark.parametrize(
    "host",
    ["http://user:pass@example.com", "http://example.com/path", "ftp://example.com"],
)
def test_reject_host(client_api, host):
    with pytest.raises(ValueError):
        client_api.normalize_host(host)


@pytest.mark.parametrize(
    "code,exception", [(1, "InvalidAuth"), (2, "SessionBusy"), (4, "GigasetError")]
)
async def test_login_error_no_logout_or_retry(client_api, code, exception):
    client = client_api.GigasetClient("base.example", "test-pin")
    with aioresponses() as mock:
        mock.get("http://base.example/login.html", body="var error = 0;")
        mock.post("http://base.example/login.html", body=f"var error = {code};")
        with pytest.raises(getattr(client_api, exception)):
            await client.async_update()
        assert sum(len(requests) for requests in mock.requests.values()) == 2


async def test_update_always_logs_out(client_api, status_html, device_html):
    client = client_api.GigasetClient("base.example", "test-pin")
    with aioresponses() as mock:
        mock.get("http://base.example/login.html", body="var error = 0;")
        mock.post(
            "http://base.example/login.html", body='<a href="logout.html">Log off</a>'
        )
        mock.get("http://base.example/status_connections.html", body=status_html)
        mock.get("http://base.example/status_device.html", body=device_html)
        mock.get("http://base.example/logout.html", body="Login")
        connections, device = await client.async_update()
        assert connections["voip_2"].registered is False
        assert device is None
        assert sum(len(requests) for requests in mock.requests.values()) == 5


async def test_parse_error_logs_out(client_api):
    client = client_api.GigasetClient("base.example", "test-pin")
    with aioresponses() as mock:
        mock.get("http://base.example/login.html", body="var error = 0;")
        mock.post(
            "http://base.example/login.html", body='<a href="logout.html">Log off</a>'
        )
        mock.get(
            "http://base.example/status_connections.html", body="Unexpected markup"
        )
        mock.get("http://base.example/status_device.html", body="Unsupported markup")
        mock.get("http://base.example/logout.html", body="Login")
        with pytest.raises(client_api.ParseError):
            await client.async_update()
        assert sum(len(requests) for requests in mock.requests.values()) == 5


async def test_reject_cross_origin_redirect(client_api):
    client = client_api.GigasetClient("base.example", "test-pin")
    with aioresponses() as mock:
        mock.get("http://base.example/login.html", body="var error = 0;")
        mock.post(
            "http://base.example/login.html",
            status=302,
            headers={"Location": "http://other.example/status_connections.html"},
        )
        with pytest.raises(client_api.GigasetError, match="Unsafe redirect"):
            await client.async_update()
        assert sum(len(requests) for requests in mock.requests.values()) == 2


async def test_pin_not_replayed_on_redirect(client_api, status_html, device_html):
    client = client_api.GigasetClient("base.example", "test-pin")
    with aioresponses() as mock:
        mock.get("http://base.example/login.html", body="var error = 0;")
        mock.post(
            "http://base.example/login.html",
            status=302,
            headers={"Location": "/home.html"},
        )
        mock.get(
            "http://base.example/home.html", body='<a href="logout.html">Log off</a>'
        )
        mock.get("http://base.example/status_connections.html", body=status_html)
        mock.get("http://base.example/status_device.html", body=device_html)
        mock.get("http://base.example/logout.html", body="Login")
        await client.async_update()
        from yarl import URL

        request = mock.requests[("GET", URL("http://base.example/home.html"))][0]
        assert request.kwargs["data"] is None


async def test_reboot_only_sends_operation_one(client_api, status_html):
    client = client_api.GigasetClient("base.example", "test-pin")
    request = AsyncMock(
        side_effect=[
            "var error = 0;",
            '<a href="logout.html">Log off</a>',
            status_html,
            '<form method="post"><input name="reboot_reset_function" value="0"></form>',
            "Restarting",
            "Login",
        ]
    )
    with patch.object(client, "_request", request):
        await client.async_reboot()
    post = request.call_args_list[4]
    assert post.args[1] == client_api.REBOOT_PAGE
    data = post.args[2]
    assert data.is_multipart
    assert data._fields[0][2] == "1"
    assert len(data._fields) == 1


async def test_lock_serializes_updates(client_api, status_html, device_html):
    client = client_api.GigasetClient("base.example", "test-pin")
    pages = []

    async def request(session, page, data=None):
        pages.append(page)
        await asyncio.sleep(0)
        if page == client_api.STATUS_PAGE:
            return status_html
        if page == "status_device.html":
            return device_html
        return '<a href="logout.html">Log off</a>'

    with patch.object(client, "_request", request):
        await asyncio.gather(client.async_update(), client.async_update())
    assert (
        pages
        == [
            "login.html",
            "login.html",
            client_api.STATUS_PAGE,
            "status_device.html",
            "logout.html",
        ]
        * 2
    )


def test_hardware_slots_survive_missing_row(client_api, status_html, device_html):
    # Account A can disappear without provider B inheriting its identity.
    start = status_html.index('<tr><td class="rightSide"><table><tr>\n<td>VoIP</td>')
    end = status_html.index("</tr></table></td></tr>", start) + len(
        "</tr></table></td></tr>"
    )
    connections = client_api.parse_connections(
        status_html[:start] + status_html[end:], device_html
    )
    assert connections["voip_2"].name == "Provider B"
    assert "voip_1" not in connections


def test_ambiguous_slot_labels_rejected(client_api, device_html):
    with pytest.raises(client_api.ParseError):
        client_api.parse_slots(device_html.replace("Provider B", "Provider A"))


def test_missing_slot_mapping_rejected(client_api, status_html, device_html):
    with pytest.raises(client_api.ParseError):
        client_api.parse_connections(
            status_html, device_html.replace("Provider B", "Different")
        )


async def test_reboot_rejects_unrecognized_form(client_api, status_html):
    client = client_api.GigasetClient("base.example", "test-pin")
    request = AsyncMock(
        side_effect=[
            "var error = 0;",
            '<a href="logout.html">Log off</a>',
            status_html,
            "Unsupported page",
            "Login",
        ]
    )
    with patch.object(client, "_request", request):
        with pytest.raises(client_api.ParseError):
            await client.async_reboot()
    assert request.call_args_list[-1].args[1] == "logout.html"
    assert all(len(call.args) == 2 for call in request.call_args_list[3:])
