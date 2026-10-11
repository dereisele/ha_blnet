"""The BLNET integration: UVR1611 via BL-NET."""
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_RESOURCE,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

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
)
from .coordinator import BLNETConfigEntry, BLNETCoordinator

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

# Old YAML configuration, only imported into a config entry
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_RESOURCE): cv.url,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_NODE): cv.positive_int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
                vol.Optional(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): cv.positive_int,
                vol.Optional(CONF_TA_PORT, default=DEFAULT_TA_PORT): cv.positive_int,
                vol.Optional(CONF_USE_WEB, default=True): cv.boolean,
                vol.Optional(CONF_USE_TA, default=False): cv.boolean,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import a YAML configuration into a config entry."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=dict(config[DOMAIN])
            )
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            "deprecated_yaml",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Set up the BL-NET from a config entry."""
    coordinator = BLNETCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
