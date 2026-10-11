"""Config flow for the BLNET integration."""
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import create_client

PORT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RESOURCE): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_USE_WEB, default=True): BooleanSelector(),
        vol.Required(CONF_USE_TA, default=False): BooleanSelector(),
        vol.Required(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): PORT_SELECTOR,
        vol.Required(CONF_TA_PORT, default=DEFAULT_TA_PORT): PORT_SELECTOR,
        vol.Optional(CONF_NODE): NumberSelector(
            NumberSelectorConfig(min=1, max=62, mode=NumberSelectorMode.BOX)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL, max=86400, unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


def _entry_data(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Entry data from form or YAML input, with ints instead of floats."""
    node = user_input.get(CONF_NODE)
    return {
        CONF_RESOURCE: user_input[CONF_RESOURCE],
        CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
        CONF_USE_WEB: user_input.get(CONF_USE_WEB, True),
        CONF_USE_TA: user_input.get(CONF_USE_TA, False),
        CONF_WEB_PORT: int(user_input.get(CONF_WEB_PORT, DEFAULT_WEB_PORT)),
        CONF_TA_PORT: int(user_input.get(CONF_TA_PORT, DEFAULT_TA_PORT)),
        CONF_NODE: None if node is None else int(node),
    }


def _title(data: Mapping[str, Any]) -> str:
    resource = data[CONF_RESOURCE]
    return urlparse(resource).hostname or resource


def _test_connection(data: Mapping[str, Any]) -> bool:
    """Connect and fetch once. Blocking. Return whether any values came back."""
    raw = create_client(data).fetch(data[CONF_NODE])
    return any(raw.get(domain) for domain in raw)


async def _validate(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    if not data[CONF_USE_WEB] and not data[CONF_USE_TA]:
        return {"base": "no_access_mode"}
    try:
        has_data = await hass.async_add_executor_job(_test_connection, data)
    except AssertionError:
        return {"base": "invalid_config"}
    except (OSError, ValueError):
        return {"base": "cannot_connect"}
    if not has_data:
        return {"base": "no_data"}
    return {}


class BLNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for BLNET."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BLNETOptionsFlow:
        """Return the options flow."""
        return BLNETOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up the BL-NET from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _entry_data(user_input)
            errors = await _validate(self.hass, data)
            if not errors:
                return self.async_create_entry(
                    title=_title(data),
                    data=data,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the YAML configuration without testing the connection."""
        data = _entry_data(import_data)
        if not data[CONF_USE_WEB] and not data[CONF_USE_TA]:
            return self.async_abort(reason="no_access_mode")
        return self.async_create_entry(
            title=_title(data),
            data=data,
            options={
                CONF_SCAN_INTERVAL: import_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the connection settings of the existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _entry_data(user_input)
            errors = await _validate(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, title=_title(data), data=data)
        suggested = user_input or {k: v for k, v in entry.data.items() if v is not None}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, suggested),
            errors=errors,
        )


class BLNETOptionsFlow(OptionsFlowWithReload):
    """Options for BLNET; changing them reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the scan interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
