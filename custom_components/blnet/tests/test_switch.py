"""Tests for the BLNET switch component."""
import unittest
from unittest.mock import Mock

from homeassistant.exceptions import HomeAssistantError

from custom_components.blnet.switch import BLNETModeSwitch, BLNETSwitch


class TestBLNETSwitch(unittest.TestCase):
    """Test the BLNETSwitch class."""

    def setUp(self):
        """Set up test variables."""
        self.communication = Mock()
        self.communication.data = {
            'blnet digital 1': {'friendly_name': 'Pump', 'mode': 'HAND', 'value': True},
        }
        self.switch = BLNETSwitch(1, 'blnet digital 1', 'Pump', self.communication)

    def test_unknown_before_first_update(self):
        """Test the state is unknown before data arrived."""
        self.assertIsNone(self.switch.is_on)

    def test_update(self):
        """Test state and mode attribute are read from the data handler."""
        self.switch.update()
        self.assertTrue(self.switch.is_on)
        self.assertEqual(self.switch.extra_state_attributes, {'mode': 'HAND'})

    def test_failed_turn_on_keeps_state(self):
        """Test the state is not changed when the command fails."""
        self.communication.turn_on.side_effect = HomeAssistantError
        with self.assertRaises(HomeAssistantError):
            self.switch.turn_on()
        self.assertIsNone(self.switch.is_on)


class TestBLNETModeSwitch(unittest.TestCase):
    """Test the BLNETModeSwitch class."""

    def setUp(self):
        """Set up test variables."""
        self.communication = Mock()
        self.communication.data = {
            'blnet digital 1': {'friendly_name': 'Pump', 'mode': 'HAND', 'value': True},
        }
        self.switch = BLNETModeSwitch(1, 'blnet digital 1', 'Pump', self.communication)

    def test_name_differs_from_output_switch(self):
        """Test the mode switch doesn't share its name with the output switch."""
        self.assertEqual(self.switch.name, 'Pump automated')

    def test_hand_mode_is_off(self):
        """Test HAND mode is reported as off."""
        self.switch.update()
        self.assertIs(self.switch.is_on, False)

    def test_auto_mode_is_on(self):
        """Test AUTO mode is reported as on."""
        self.communication.data['blnet digital 1']['mode'] = 'AUTO'
        self.switch.update()
        self.assertIs(self.switch.is_on, True)

    def test_turn_off_keeps_output_value(self):
        """Test switching to HAND keeps the output's current value."""
        self.switch.update()
        self.switch.turn_off()
        self.communication.turn_on.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
