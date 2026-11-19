"""Collect and validate the host and system PIN through Home Assistant."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import GigasetClient, GigasetError, InvalidAuth, SessionBusy
from .const import CONF_PIN, DOMAIN


def schema(host=None):
    """Never prefill the secret, including during reauthentication."""
    return vol.Schema(
        {
            vol.Required("host", default=host or ""): str,
            vol.Required(CONF_PIN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


class GigasetFlow(ConfigFlow, domain=DOMAIN):
    """Configure one entry per physical base."""

    VERSION = 1

    async def _validate(self, user_input):
        pin = user_input[CONF_PIN]
        if len(pin) != 4 or not pin.isascii() or not pin.isdigit():
            raise InvalidAuth("Expected four digits")
        client = GigasetClient(user_input["host"], pin)
        _, device = await client.async_update(include_device=True)
        return device, {"host": client.base_url, CONF_PIN: pin}

    async def async_step_user(self, user_input=None):
        """Handle setup without submitting configuration to the phone."""
        errors = {}
        if user_input is not None:
            try:
                device, data = await self._validate(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except SessionBusy:
                errors["base"] = "session_busy"
            except GigasetError, ValueError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(device.mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=device.model, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=schema((user_input or {}).get("host")),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        """Replace the PIN instead of retrying bad credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Verify the same physical base before updating its credentials."""
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            try:
                device, data = await self._validate(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except SessionBusy:
                errors["base"] = "session_busy"
            except GigasetError, ValueError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(device.mac)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema(entry.data["host"]),
            errors=errors,
        )
