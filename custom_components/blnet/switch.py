"""Switches for the digital outputs of the UVR1611."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_USE_WEB
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity

# One command at a time to the web interface
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add two switches per digital output, if the web interface is used."""
    if not entry.data[CONF_USE_WEB]:
        return
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_switches() -> None:
        new: list[SwitchEntity] = []
        for blnet_id, data in coordinator.data.items():
            if data["domain"] == "digital" and blnet_id not in known:
                known.add(blnet_id)
                new += [
                    BLNETOutputSwitch(coordinator, blnet_id),
                    BLNETModeSwitch(coordinator, blnet_id),
                ]
        if new:
            async_add_entities(new)

    add_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(add_new_switches))


class BLNETOutputSwitch(BLNETEntity, SwitchEntity):
    """Switch a digital output on or off. Sets the output to HAND."""

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, blnet_id, "output")
        self._attr_unique_id = f"blnet_switch_{self.output_id}"

    @property
    def is_on(self) -> bool:
        """Return whether the output is on."""
        return self.blnet_data["value"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return AUTO or HAND."""
        return {"mode": self.blnet_data["mode"]}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the output on (HAND/EIN)."""
        await self.coordinator.async_set_output(self.output_id, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the output off (HAND/AUS)."""
        await self.coordinator.async_set_output(self.output_id, "off")


class BLNETModeSwitch(BLNETEntity, SwitchEntity):
    """On means the controller switches the output (AUTO)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the switch."""
        named = bool(coordinator.data[blnet_id]["name"])
        super().__init__(
            coordinator, blnet_id, "output_mode_named" if named else "output_mode"
        )
        self._attr_unique_id = f"blnet_mode_switch_{self.output_id}"
        if named:
            # The name comes from the translation with the output's name in it
            del self._attr_name
            self._attr_translation_placeholders = {
                "name": coordinator.data[blnet_id]["name"]
            }

    @property
    def is_on(self) -> bool:
        """Return whether the output is in AUTO mode."""
        return self.blnet_data["mode"] != "HAND"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Hand control back to the controller (AUTO)."""
        await self.coordinator.async_set_output(self.output_id, "auto")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch to HAND, keeping the output's current value."""
        state = "on" if self.blnet_data["value"] else "off"
        await self.coordinator.async_set_output(self.output_id, state)
