"""Minimal diagnostics without credentials, addresses, or account labels."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "last_update_success": coordinator.last_update_success,
        "poll_status": coordinator.poll_status,
        "last_successful_update": (
            coordinator.last_success.isoformat() if coordinator.last_success else None
        ),
        "connections": [
            {
                "slot": connection.slot,
                "kind": connection.kind,
                "status": connection.status,
            }
            for connection in (coordinator.data or {}).values()
        ],
    }
