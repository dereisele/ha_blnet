"""
Connect to a BL-NET via it's web interface and read and write data

Switch to control digital outputs
"""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'blnet'

MODE = 'mode'


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the BLNET component"""

    if discovery_info is None:
        _LOGGER.error("No BL-Net communication configured")
        return False

    switch_id = discovery_info['id']
    blnet_id = discovery_info['blnet_id']
    name = discovery_info['name']
    comm = hass.data[f'DATA_{DOMAIN}']

    add_devices([BLNETSwitch(switch_id, blnet_id, name, comm),
                 BLNETModeSwitch(switch_id, blnet_id, name, comm)], True)
    return True


class BLNETSwitch(SwitchEntity):
    """
    Representation of a switch that toggles a digital output of the UVR1611.
    """

    def __init__(self, switch_id, blnet_id, name, comm):
        """Initialize the switch."""
        self._blnet_id = blnet_id
        self._id = switch_id
        self.communication = comm
        self._name = name
        self._state = STATE_UNKNOWN
        self._assumed_state = True
        self._icon = None
        self._mode = STATE_UNKNOWN
        self._last_updated = None

    @property
    def unique_id(self):
        """Home assist requires a unique ID property."""
        return f"blnet_switch_{self._id}"
    
    def update(self):
        """Get the latest data from communication device """
        # check if new data has arrived
        last_blnet_update = self.communication.last_updated()

        if last_blnet_update == self._last_updated:
            return

        sensor_data = self.communication.data.get(self._blnet_id)

        if sensor_data is None:
            return

        if sensor_data.get('value'):
            self._state = STATE_ON
            self._icon = 'mdi:flash'
        # Nonautomated switch, toggled off => switch off
        else:
            self._state = STATE_OFF
            self._icon = 'mdi:flash-off'
        self._mode = sensor_data.get('mode')

        self._last_updated = last_blnet_update
        self._assumed_state = False

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def available(self):
        """Return False if the last fetch from the BL-NET failed."""
        return self.communication.available

    @property
    def icon(self):
        """Return the state of the device."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        return {MODE: self._mode}

    @property
    def is_on(self):
        """Return true if device is on, None if unknown."""
        if self._state == STATE_UNKNOWN:
            return None
        return self._state == STATE_ON

    def turn_on(self, **kwargs):
        """Turn the device on."""
        self.communication.turn_on(self._id)
        self._state = STATE_ON
        self._assumed_state = True

    def turn_off(self, **kwargs):
        """Turn the device off."""
        self.communication.turn_off(self._id)
        self._state = STATE_OFF
        self._assumed_state = True

    @property
    def assumed_state(self) -> bool:
        return self._assumed_state


class BLNETModeSwitch(SwitchEntity):
    """
    Representation of a switch that toggles the operation mode
    of a digital output of the UVR1611. On means automated
    """

    def __init__(self, switch_id, blnet_id, name, comm):
        """Initialize the switch."""
        self._blnet_id = blnet_id
        self._id = switch_id
        self.communication = comm
        self._name = f"{name} automated"
        self._state = STATE_UNKNOWN
        self._activated = None
        self._assumed_state = True
        self._icon = None
        self._last_updated = None

    @property
    def unique_id(self):
        """Return a unique ID for the mode switch."""
        return f"blnet_mode_switch_{self._id}"
    
    def update(self):
        """Get the latest data from communication device """
        # check if new data has arrived
        last_blnet_update = self.communication.last_updated()

        if last_blnet_update == self._last_updated:
            return

        sensor_data = self.communication.data.get(self._blnet_id)

        if sensor_data is None:
            return

        if sensor_data.get('mode') == 'HAND':
            self._state = STATE_OFF
            self._icon = 'mdi:cog-off'
        else:
            self._state = STATE_ON
            self._icon = 'mdi:cog'
        
        self._activated = sensor_data.get('value')

        self._last_updated = last_blnet_update
        self._assumed_state = False

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def available(self):
        """Return False if the last fetch from the BL-NET failed."""
        return self.communication.available

    @property
    def icon(self):
        """Return the state of the device."""
        return self._icon

    @property
    def is_on(self):
        """Return true if device is on, None if unknown."""
        if self._state == STATE_UNKNOWN:
            return None
        return self._state == STATE_ON

    def turn_on(self, **kwargs):
        """Turn the device on."""
        self.communication.turn_auto(self._id)
        self._state = STATE_ON
        self._assumed_state = True

    def turn_off(self, **kwargs):
        """Turn the device off, in this case meaning to turn off automation,
        an sending a HAND/EIN or HAND/AUS turn manual control on."""

        if self._activated:
            self.communication.turn_on(self._id)
        else:
            self.communication.turn_off(self._id)
        self._state = STATE_OFF
        self._assumed_state = True

    @property
    def assumed_state(self)->bool:
        return self._assumed_state
