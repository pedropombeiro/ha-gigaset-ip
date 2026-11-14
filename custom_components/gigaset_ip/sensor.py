"""Diagnostic sensors that remain readable after a failed poll."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

STATUSES = [
    "unknown",
    "ok",
    "session_busy",
    "invalid_auth",
    "unsupported_response",
    "communication_error",
]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            GigasetDiagnostic(entry.runtime_data, "last_successful_update"),
            GigasetDiagnostic(entry.runtime_data, "poll_status"),
        ]
    )


class GigasetDiagnostic(CoordinatorEntity, SensorEntity):
    """Retain the last success time instead of replacing it with unavailable."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.device.mac}_{key}"
        self._attr_device_info = coordinator.device_info
        self._attr_device_class = (
            SensorDeviceClass.TIMESTAMP
            if key == "last_successful_update"
            else SensorDeviceClass.ENUM
        )
        if key == "poll_status":
            self._attr_options = STATUSES

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return (
            self.coordinator.last_success
            if self.key == "last_successful_update"
            else self.coordinator.poll_status
        )
