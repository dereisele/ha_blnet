"""Tests for the BLNET switch component."""
import unittest
from unittest.mock import Mock

from homeassistant.exceptions import HomeAssistantError

from custom_components.blnet.switch import BLNETSwitch


class TestBLNETSwitch(unittest.TestCase):
    """Test the BLNETSwitch class."""

    def setUp(self):
        """Set up test variables."""
        self.communication = Mock()
        self.switch = BLNETSwitch(1, 'blnet digital 1', 'Pump', self.communication)

    def test_failed_turn_on_keeps_state(self):
        """Test the state is not changed when the command fails."""
        self.communication.turn_on.side_effect = HomeAssistantError
        with self.assertRaises(HomeAssistantError):
            self.switch.turn_on()
        self.assertFalse(self.switch.is_on)


if __name__ == '__main__':
    unittest.main()
