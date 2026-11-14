"""Exercise config entries, entity state, and errors inside Home Assistant."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gigaset_ip.api import (
    Connection,
    Device,
    InvalidAuth,
    SessionBusy,
)
from custom_components.gigaset_ip.const import DOMAIN
from custom_components.gigaset_ip.coordinator import GigasetCoordinator

DEVICE = Device("02:00:00:00:00:01", "Example base", "123456")
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
    assert await hass.config_entries.async_unload(entry.entry_id)
