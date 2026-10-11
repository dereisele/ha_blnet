"""Data update coordinator for the BLNET integration."""
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyblnet import BLNET

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
    SENSOR_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)

type BLNETConfigEntry = ConfigEntry[BLNETCoordinator]


def create_client(data: Mapping[str, Any]) -> BLNET:
    """Create the pyblnet client. Blocking: connects in the constructor."""
    return BLNET(
        data[CONF_RESOURCE],
        password=data.get(CONF_PASSWORD),
        web_port=int(data.get(CONF_WEB_PORT, DEFAULT_WEB_PORT)),
        ta_port=int(data.get(CONF_TA_PORT, DEFAULT_TA_PORT)),
        use_web=data.get(CONF_USE_WEB, True),
        use_ta=data.get(CONF_USE_TA, False),
    )


def _digital_to_bool(value: Any) -> bool:
    """The web interface reports "EIN"/"AUS", BLNET direct reports 1/0."""
    if isinstance(value, str):
        return value == "EIN"
    return bool(value)


def normalize(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten pyblnet's fetch() result, keyed like the entity unique IDs."""
    data: dict[str, dict[str, Any]] = {}
    for domain in SENSOR_DOMAINS:
        for key, entry in raw.get(domain, {}).items():
            data[f"{DOMAIN} {domain} {key}"] = {
                "id": key,
                "domain": domain,
                "name": entry.get("name"),
                "value": entry.get("value"),
                # Analog inputs have a type (temperature, volume_flow, ...)
                "type": entry.get("type") if domain == "analog" else domain,
                "mode": None,
            }
    for key, entry in raw.get("digital", {}).items():
        data[f"{DOMAIN} digital {key}"] = {
            "id": key,
            "domain": "digital",
            "name": entry.get("name"),
            "value": _digital_to_bool(entry.get("value")),
            "type": None,
            "mode": entry.get("mode"),
        }
    return data


class BLNETCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch data from the BL-NET."""

    config_entry: BLNETConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BLNETConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client: BLNET | None = None

    @property
    def _node(self) -> int | None:
        return self.config_entry.data.get(CONF_NODE)

    def _fetch(self) -> dict[str, Any]:
        if self.client is None:
            self.client = create_client(self.config_entry.data)
        return self.client.fetch(self._node)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            raw = await self.hass.async_add_executor_job(self._fetch)
        except (OSError, ValueError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        return normalize(raw)

    async def async_set_output(self, output_id: int, state: str) -> None:
        """Set a digital output to "on", "off" or "auto" via the web interface."""
        assert self.client is not None
        turn = {
            "on": self.client.turn_on,
            "off": self.client.turn_off,
            "auto": self.client.turn_auto,
        }[state]
        try:
            await self.hass.async_add_executor_job(turn, output_id, self._node)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"output": str(output_id), "state": state},
            ) from err
        await self.async_request_refresh()
