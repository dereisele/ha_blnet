"""
Connect to a BL-NET via it's web interface and read and write data
"""
import logging

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

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'blnet'

# Sensor type (analog input type, or the domain otherwise) ->
# device class, state class, unit, icon
SENSOR_TYPES = {
    'temperature': (SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT,
                    UnitOfTemperature.CELSIUS, None),
    'volume_flow': (SensorDeviceClass.VOLUME_FLOW_RATE, SensorStateClass.MEASUREMENT,
                    UnitOfVolumeFlowRate.LITERS_PER_HOUR, None),
    'radiation': (SensorDeviceClass.IRRADIANCE, SensorStateClass.MEASUREMENT,
                  UnitOfIrradiance.WATTS_PER_SQUARE_METER, None),
    'power': (SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT,
              UnitOfPower.KILO_WATT, None),
    'energy': (SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
               UnitOfEnergy.KILO_WATT_HOUR, None),
    # Speed level 0-30, not rpm
    'speed': (None, SensorStateClass.MEASUREMENT, None, 'mdi:speedometer'),
}


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the BLNET component"""

    if discovery_info is None:
        _LOGGER.error("No BL-Net communication configured")
        return False

    sensor_id = discovery_info['id']
    blnet_id = discovery_info['blnet_id']
    name = discovery_info['name']
    friendly_name = discovery_info['friendly_name']
    _LOGGER.debug(f"Discovery info: {discovery_info}")
    comm = hass.data[f'DATA_{DOMAIN}']

    add_devices([BLNETComponent(hass, sensor_id, name, blnet_id, friendly_name, comm)], True)
    return True


class BLNETComponent(SensorEntity):
    """Implementation of a BL-NET - UVR1611 sensor."""

    def __init__(self, hass, sensor_id, name, blnet_id, friendly_name, communication):
        """Initialize the BL-NET sensor."""
        self._identifier = blnet_id
        self.communication = communication
        self._name = name
        self._friendly_name = friendly_name
        self._state = None
        self._type = None

    @property
    def friendly_name(self):
        """Return the friendly name of the sensor."""
        return self._friendly_name

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return f"blnet_sensor_{self._identifier}"

    @property
    def available(self):
        """Return False if the last fetch from the BL-NET failed."""
        return self.communication.available

    @property
    def native_value(self):
        """Return the value of the sensor."""
        return self._state

    @property
    def device_class(self):
        """Return the device class of the sensor type."""
        return SENSOR_TYPES.get(self._type, (None,) * 4)[0]

    @property
    def state_class(self):
        """Return the state class of the sensor type."""
        return SENSOR_TYPES.get(self._type, (None,) * 4)[1]

    @property
    def native_unit_of_measurement(self):
        """Return the unit of the sensor type."""
        return SENSOR_TYPES.get(self._type, (None,) * 4)[2]

    @property
    def icon(self):
        """Return the icon of the sensor type."""
        return SENSOR_TYPES.get(self._type, (None,) * 4)[3]

    def update(self):
        """Get the latest data from communication device """
        sensor_data = self.communication.data.get(self._identifier)
        
        if sensor_data is None:
            _LOGGER.warning(f"No data found for sensor {self._identifier}")
            return

        _LOGGER.debug(f"Found sensor data: {sensor_data}")
        self._friendly_name = sensor_data.get('friendly_name')
        self._state = sensor_data.get('value')
        self._type = sensor_data.get('type')
