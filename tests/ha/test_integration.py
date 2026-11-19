"""Exercise config entries, entity state, and errors inside Home Assistant."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gigaset_ip.api import (
    BaseTimestamp,
    Connection,
    Device,
    InvalidAuth,
    ParseError,
    SessionBusy,
)
from custom_components.gigaset_ip.const import DOMAIN
from custom_components.gigaset_ip.coordinator import GigasetCoordinator

DEVICE = Device(
    "02:00:00:00:00:01",
    "Example base",
    "42.263",
    BaseTimestamp(datetime(2026, 1, 10, 1, 50), "ok"),
    BaseTimestamp(datetime(2026, 1, 9, 10, 11), "ok"),
)
DATA = {
    "voip_1": Connection("voip_1", "Provider A", "Registered", "VoIP"),
    "voip_2": Connection("voip_2", "Provider B", "Registration failed.", "VoIP"),
    "voip_3": Connection("voip_3", "Unused", "Disabled", "VoIP"),
}


async def test_setup_flow(hass):
    with (
        patch(
            "custom_components.gigaset_ip.config_flow.GigasetClient.async_update",
            return_value=(DATA, DEVICE),
        ),
        patch("custom_components.gigaset_ip.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "base.example", "pin": "".join(map(str, range(1, 5)))},
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["result"].unique_id == DEVICE.mac
    assert result["data"]["host"] == "http://base.example/"


async def test_reauth_wrong_base_uses_translated_abort_reason(hass):
    original_data = {"host": "http://base.example/", "pin": "unused"}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE.mac, data=original_data)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"
    with patch(
        "custom_components.gigaset_ip.config_flow.GigasetClient.async_update",
        return_value=(DATA, replace(DEVICE, mac="02:00:00:00:00:02")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "other-base.example", "pin": "".join(map(str, range(1, 5)))},
        )
    assert result["type"] == "abort"
    assert result["reason"] == "wrong_account"
    assert entry.data == original_data
    assert entry.unique_id == DEVICE.mac


@pytest.mark.parametrize(
    "error,key", [(InvalidAuth(), "invalid_auth"), (SessionBusy(), "session_busy")]
)
async def test_setup_errors(hass, error, key):
    with patch(
        "custom_components.gigaset_ip.config_flow.GigasetClient.async_update",
        side_effect=error,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "base.example", "pin": "".join(map(str, range(1, 5)))},
        )
    assert result["errors"] == {"base": key}


async def test_coordinator_distinguishes_busy_and_bad_pin(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    client = AsyncMock()
    coordinator = GigasetCoordinator(hass, entry, client)
    client.async_update.side_effect = SessionBusy()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    client.async_update.side_effect = InvalidAuth()
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_entities_and_unload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE.mac,
        data={"host": "base.example", "pin": "unused"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.gigaset_ip.api.GigasetClient.async_update",
        return_value=(DATA, DEVICE),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    states = [
        state
        for state in hass.states.async_all()
        if state.domain == Platform.BINARY_SENSOR
    ]
    assert sorted(state.state for state in states) == ["off", "on"]
    entry.runtime_data.last_update_success = False
    entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()
    assert all(
        hass.states.get(state.entity_id).state == "unavailable" for state in states
    )
    diagnostics = [s for s in hass.states.async_all() if s.domain == "sensor"]
    assert len(diagnostics) == 4
    assert all(s.state not in {"unknown", "unavailable"} for s in diagnostics)
    timestamp_states = [s for s in diagnostics if "reported_status" in s.attributes]
    assert len(timestamp_states) == 2
    assert all(s.attributes["device_class"] == "timestamp" for s in timestamp_states)
    assert all(s.attributes["reported_status"] == "ok" for s in timestamp_states)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE.mac), entry.entry_id
    )
    assert device.sw_version == "42.263"
    with patch(
        "custom_components.gigaset_ip.api.GigasetClient.async_update",
        return_value=(DATA, replace(DEVICE, firmware="42.264")),
    ):
        await entry.runtime_data.async_refresh()
    assert registry.async_get(device.id).sw_version == "42.264"
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "error,status",
    [(SessionBusy(), "session_busy"), (ParseError(), "unsupported_response")],
)
async def test_diagnostics_retain_last_success(hass, error, status):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    client = AsyncMock()
    client.async_update.return_value = DATA, DEVICE
    coordinator = GigasetCoordinator(hass, entry, client)
    await coordinator._async_update_data()
    timestamp = coordinator.last_success
    assert coordinator.poll_status == "ok"
    client.async_update.side_effect = error
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.poll_status == status
    assert coordinator.last_success == timestamp


async def test_refresh_button_works_after_poll_failure(hass):
    from custom_components.gigaset_ip.button import GigasetRefresh

    entry = MockConfigEntry(domain=DOMAIN, data={})
    coordinator = GigasetCoordinator(hass, entry, AsyncMock())
    coordinator.device = DEVICE
    coordinator.last_update_success = False
    button = GigasetRefresh(coordinator)
    assert button.available
    with patch.object(
        coordinator, "async_request_refresh", new_callable=AsyncMock
    ) as refresh:
        await button.async_press()
    refresh.assert_awaited_once()


async def test_base_timestamps_refresh_and_survive_failure(hass):
    await hass.config.async_set_time_zone("Europe/Zurich")
    client = AsyncMock()
    client.async_update.return_value = DATA, DEVICE
    coordinator = GigasetCoordinator(
        hass, MockConfigEntry(domain=DOMAIN, data={}), client
    )
    await coordinator._async_update_data()
    first = dict(coordinator.timestamps)
    assert first["last_ntp_sync"].value == datetime(2026, 1, 10, 0, 50, tzinfo=UTC)
    await coordinator._async_update_data()
    assert coordinator.timestamps == first
    client.async_update.assert_awaited_with(include_device=True)
    updated = BaseTimestamp(datetime(2026, 1, 11, 1, 50), "ok")
    client.async_update.return_value = DATA, replace(DEVICE, last_ntp_sync=updated)
    await coordinator._async_update_data()
    assert coordinator.timestamps["last_ntp_sync"].value == datetime(
        2026, 1, 11, 0, 50, tzinfo=UTC
    )
    first = dict(coordinator.timestamps)
    client.async_update.side_effect = SessionBusy()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.timestamps == first
    client.async_update.side_effect = None
    client.async_update.return_value = (
        DATA,
        Device(
            DEVICE.mac,
            DEVICE.model,
            DEVICE.firmware,
            BaseTimestamp(status="invalid"),
            BaseTimestamp(status="not_reported"),
        ),
    )
    await coordinator._async_update_data()
    assert coordinator.timestamps["last_ntp_sync"].value == first["last_ntp_sync"].value
    assert coordinator.timestamps["last_ntp_sync"].status == "invalid"
    assert coordinator.poll_status == "ok"
    client.async_update.return_value = (
        DATA,
        Device(
            DEVICE.mac, DEVICE.model, DEVICE.firmware, BaseTimestamp(status="never")
        ),
    )
    await coordinator._async_update_data()
    assert coordinator.timestamps["last_ntp_sync"] == BaseTimestamp(status="never")


@pytest.mark.parametrize(
    "wall_time", [datetime(2026, 3, 29, 2, 30), datetime(2026, 10, 25, 2, 30)]
)
async def test_ambiguous_or_nonexistent_base_time(hass, wall_time):
    await hass.config.async_set_time_zone("Europe/Zurich")
    client = AsyncMock()
    client.async_update.return_value = (
        DATA,
        Device(
            DEVICE.mac, DEVICE.model, DEVICE.firmware, BaseTimestamp(wall_time, "ok")
        ),
    )
    coordinator = GigasetCoordinator(
        hass, MockConfigEntry(domain=DOMAIN, data={}), client
    )
    await coordinator._async_update_data()
    assert coordinator.timestamps["last_ntp_sync"] == BaseTimestamp(status="invalid")
