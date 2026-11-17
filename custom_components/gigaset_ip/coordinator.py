"""Share a short authenticated poll between every entity."""

import logging
from datetime import UTC, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BaseTimestamp, GigasetError, InvalidAuth, ParseError, SessionBusy
from .const import DOMAIN


class GigasetCoordinator(DataUpdateCoordinator):
    """Poll at five-minute intervals; failed polls mark entities unavailable."""

    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=5),
        )
        self.client = client
        self._entry_id = entry.entry_id
        self.device = None
        self.last_success = None
        self.poll_status = "unknown"
        self.timestamps = {}

    async def _async_update_data(self):
        try:
            connections, device = await self.client.async_update(include_device=True)
        except InvalidAuth as error:
            self.poll_status = "invalid_auth"
            raise ConfigEntryAuthFailed("System PIN rejected") from error
        except SessionBusy as error:
            self.poll_status = "session_busy"
            raise UpdateFailed("Web configurator session busy") from error
        except ParseError as error:
            self.poll_status = "unsupported_response"
            raise UpdateFailed("Unsupported base response") from error
        except GigasetError as error:
            self.poll_status = "communication_error"
            raise UpdateFailed(
                "Base unavailable, session busy, or unsupported response"
            ) from error
        if device is not None:
            if self.device is not None and device.firmware != self.device.firmware:
                registry = dr.async_get(self.hass)
                if registered := registry.async_get_device_by_identifier(
                    (DOMAIN, device.mac), self._entry_id
                ):
                    registry.async_update_device(
                        registered.id, sw_version=device.firmware
                    )
            self.device = device
            # The configured zone is preloaded; looking it up by name can read
            # the tz database from disk and block the event loop.
            zone = dt_util.get_default_time_zone()
            for key in ("last_ntp_sync", "boot_time"):
                reading = getattr(device, key)
                value = reading.value
                if value is not None:
                    # Reject ambiguous/nonexistent DST wall times rather than
                    # silently claiming a boot or NTP sync at the wrong instant.
                    local = value.replace(tzinfo=zone)
                    alternate = local.replace(fold=1)
                    if (
                        local.utcoffset() != alternate.utcoffset()
                        or local.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
                        != value
                    ):
                        reading = BaseTimestamp(status="invalid")
                    else:
                        reading = BaseTimestamp(local.astimezone(UTC), "ok")
                if reading.status in {"invalid", "not_reported"}:
                    previous = self.timestamps.get(key)
                    if previous is not None:
                        reading = BaseTimestamp(previous.value, reading.status)
                self.timestamps[key] = reading
        self.last_success = dt_util.utcnow()
        self.poll_status = "ok"
        return connections

    @property
    def device_info(self):
        """Use the same MAC connection as UniFi for registry merging."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.mac)},
            connections={(CONNECTION_NETWORK_MAC, self.device.mac)},
            name="Gigaset IP",
            manufacturer="Gigaset Communications GmbH",
            model=self.device.model,
            sw_version=self.device.firmware,
            configuration_url=self.client.base_url,
        )
