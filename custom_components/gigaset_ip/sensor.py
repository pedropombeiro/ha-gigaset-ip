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
            GigasetDiagnostic(entry.runtime_data, "last_ntp_sync"),
            GigasetDiagnostic(entry.runtime_data, "boot_time"),
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
            if key != "poll_status"
            else SensorDeviceClass.ENUM
        )
        if key == "poll_status":
            self._attr_options = STATUSES

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        if self.key == "last_successful_update":
            return self.coordinator.last_success
        if self.key == "poll_status":
            return self.coordinator.poll_status
        reading = self.coordinator.timestamps.get(self.key)
        return reading.value if reading else None

    @property
    def extra_state_attributes(self):
        if self.key in {"last_ntp_sync", "boot_time"}:
            reading = self.coordinator.timestamps.get(self.key)
            return {
                "reported_status": reading.status if reading else "not_reported",
                "assumed_time_zone": self.hass.config.time_zone,
            }
        return None
