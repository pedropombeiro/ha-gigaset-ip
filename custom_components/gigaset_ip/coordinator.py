"""Share a short authenticated poll between every entity."""

import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GigasetError, InvalidAuth, ParseError, SessionBusy
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
        self.device = None
        self.last_success = None
        self.poll_status = "unknown"

    async def _async_update_data(self):
        try:
            connections, device = await self.client.async_update(
                include_device=self.device is None
            )
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
            self.device = device
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
