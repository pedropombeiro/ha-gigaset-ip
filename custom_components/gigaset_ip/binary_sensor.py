"""Connectivity entities for the base's connection slots."""

from importlib import import_module

from homeassistant.const import Platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_platform = import_module(f"homeassistant.components.{Platform.BINARY_SENSOR}")
BinarySensorEntity = _platform.BinarySensorEntity
BinarySensorDeviceClass = _platform.BinarySensorDeviceClass


async def async_setup_entry(hass, entry, async_add_entities):
    """Discover slots on startup and when new accounts appear."""
    coordinator = entry.runtime_data
    known = set()

    def discover():
        entities = []
        for slot, connection in (coordinator.data or {}).items():
            if slot not in known:
                known.add(slot)
                entities.append(GigasetRegistration(coordinator, slot, connection))
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class GigasetRegistration(CoordinatorEntity, BinarySensorEntity):
    """Unknown states remain unknown, not disconnected."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, slot, connection):
        super().__init__(coordinator)
        self.slot = slot
        self._attr_unique_id = f"{coordinator.device.mac}_{slot}"
        self._attr_name = f"{connection.name} registration"
        self._attr_entity_registry_enabled_default = connection.enabled_by_default
        self._attr_device_info = coordinator.device_info

    @property
    def available(self):
        """A missing slot is not proof of failed registration."""
        return super().available and self.slot in self.coordinator.data

    @property
    def is_on(self):
        connection = self.coordinator.data.get(self.slot)
        return connection.registered if connection else None

    @property
    def extra_state_attributes(self):
        connection = self.coordinator.data.get(self.slot)
        if connection is None:
            return {}
        return {
            "registration_status": connection.status,
            "connection_type": connection.kind,
        }
