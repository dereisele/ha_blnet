"""Sensors for the BLNET integration."""
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_USE_WEB, SENSOR_DOMAINS
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity

# The coordinator polls, entities don't
PARALLEL_UPDATES = 0

# Sensor type (analog input type, or the domain otherwise) ->
# device class, state class, unit
SENSOR_TYPES = {
    "temperature": (SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT,
                    UnitOfTemperature.CELSIUS),
    "volume_flow": (SensorDeviceClass.VOLUME_FLOW_RATE, SensorStateClass.MEASUREMENT,
                    UnitOfVolumeFlowRate.LITERS_PER_HOUR),
    "radiation": (SensorDeviceClass.IRRADIANCE, SensorStateClass.MEASUREMENT,
                  UnitOfIrradiance.WATTS_PER_SQUARE_METER),
    "power": (SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT),
    "energy": (SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
               UnitOfEnergy.KILO_WATT_HOUR),
    # Speed level 0-30, not rpm
    "speed": (None, SensorStateClass.MEASUREMENT, None),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors, and more whenever new values appear."""
    coordinator = entry.runtime_data
    domains = SENSOR_DOMAINS if entry.data[CONF_USE_WEB] else (*SENSOR_DOMAINS, "digital")
    known: set[str] = set()

    @callback
    def add_new_sensors() -> None:
        new = [
            BLNETSensor(coordinator, blnet_id)
            for blnet_id, data in coordinator.data.items()
            if data["domain"] in domains and blnet_id not in known
        ]
        known.update(sensor.blnet_id for sensor in new)
        if new:
            async_add_entities(new)

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


class BLNETSensor(BLNETEntity, SensorEntity):
    """A value of the BL-NET."""

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the sensor."""
        domain = coordinator.data[blnet_id]["domain"]
        # Digital outputs shown as sensors are named "Output <id>"
        super().__init__(coordinator, blnet_id, "output" if domain == "digital" else None)
        # Unchanged from the YAML setup, so existing entities are kept
        self._attr_unique_id = f"blnet_sensor_{blnet_id}"
        device_class, state_class, unit = SENSOR_TYPES.get(
            coordinator.data[blnet_id]["type"], (None, None, None)
        )
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.blnet_data["value"]
