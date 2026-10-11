"""Base entity for the BLNET integration."""
from typing import Any

from homeassistant.const import CONF_RESOURCE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BLNETCoordinator


class BLNETEntity(CoordinatorEntity[BLNETCoordinator]):
    """An entity for one value of the BL-NET."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BLNETCoordinator,
        blnet_id: str,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the entity for coordinator.data[blnet_id]."""
        super().__init__(coordinator)
        self.blnet_id = blnet_id
        data = coordinator.data[blnet_id]
        url = coordinator.config_entry.data[CONF_RESOURCE]
        if "://" not in url:
            url = f"http://{url}"
        self.output_id: int = data["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Technische Alternative",
            model="BL-NET",
            name="BL-NET",
            configuration_url=url,
        )
        # The translation key also selects the icon from icons.json
        self._attr_translation_key = translation_key or data["domain"]
        self._attr_translation_placeholders = {"id": str(data["id"])}
        if data["name"]:
            # Names configured on the controller, from the web interface
            self._attr_name = data["name"]

    @property
    def blnet_data(self) -> dict[str, Any]:
        """The current data of this entity; only valid while available."""
        return self.coordinator.data[self.blnet_id]

    @property
    def available(self) -> bool:
        """Unavailable if the update failed or this value is missing."""
        return super().available and self.blnet_id in self.coordinator.data
