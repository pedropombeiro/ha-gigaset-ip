"""Explicit reboot action. No background remediation."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GigasetError


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [GigasetRestart(entry.runtime_data), GigasetRefresh(entry.runtime_data)]
    )


class GigasetRefresh(CoordinatorEntity, ButtonEntity):
    """Allow a fresh poll even after a failed update."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.mac}_refresh"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self):
        return True

    async def async_press(self):
        await self.coordinator.async_request_refresh()


class GigasetRestart(CoordinatorEntity, ButtonEntity):
    """Restart every connection and interrupt any ongoing call."""

    _attr_has_entity_name = True
    _attr_translation_key = "restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.mac}_restart"
        self._attr_device_info = coordinator.device_info

    async def async_press(self):
        try:
            await self.coordinator.client.async_reboot()
        except GigasetError as error:
            raise HomeAssistantError(
                "Reboot was not confirmed. Check the base before trying again."
            ) from error
