"""Diagnostics for the BLNET integration."""
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import BLNETConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BLNETConfigEntry
) -> dict[str, Any]:
    """Return the configuration and the last data, without the password."""
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), {CONF_PASSWORD}),
            "options": dict(entry.options),
        },
        "data": entry.runtime_data.data,
    }
