"""Tests for the BLNET sensor component."""
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from homeassistant.exceptions import HomeAssistantError

from custom_components.blnet import BLNETConnector, BLNETDataHandler
from custom_components.blnet.sensor import BLNETComponent


class TestBLNETComponent(unittest.TestCase):
    """Test the BLNETComponent class."""

    def setUp(self):
        """Set up test variables."""
        self.hass = Mock()
        self.communication = Mock()
        self.communication.data = {}
        self.communication.last_updated = Mock(return_value=datetime.now())

    def test_init_with_numeric_sensor_id(self):
        """Test initialization with numeric sensor_id."""
        sensor = BLNETComponent(
            hass=self.hass,
            sensor_id=1,
            name="test_sensor",
            blnet_id="test_blnet_1",
            friendly_name="Test Sensor",
            communication=self.communication
        )
        self.assertEqual(sensor._identifier, "test_blnet_1")
        self.assertEqual(sensor._friendly_name, "Test Sensor")
        self.assertEqual(sensor._name, "test_sensor")
        self.assertEqual(sensor.name, "test_sensor")

    def test_init_with_string_sensor_id(self):
        """Test initialization with string sensor_id."""
        sensor = BLNETComponent(
            hass=self.hass,
            sensor_id="A1",
            name="test_sensor",
            blnet_id="test_blnet_A1",
            friendly_name="Test Sensor",
            communication=self.communication
        )
        self.assertEqual(sensor._identifier, "test_blnet_A1")
        self.assertEqual(sensor._friendly_name, "Test Sensor")


class TestBLNETDataHandler(unittest.TestCase):
    """Test the BLNETDataHandler class."""

    def setUp(self):
        """Set up test variables."""
        self.hass = Mock()
        self.blnet = Mock()
        self.config = {
            'resource': 'http://example.com',
            'password': 'test',
            'web_port': 80,
            'ta_port': 40000,
            'use_web': True,
            'use_ta': False
        }
        self.node = 1

    def test_init(self):
        """Test initialization of data handler."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.assertEqual(handler.blnet, self.blnet)
        self.assertEqual(handler.node, self.node)
        self.assertEqual(handler._hass, self.hass)
        self.assertEqual(handler._config, self.config)
        self.assertEqual(handler.data, {})
        self.assertIsNone(handler._last_updated)

    def test_last_updated(self):
        """Test last_updated method."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.assertIsNone(handler.last_updated())
        handler._last_updated = datetime.now()
        self.assertIsNotNone(handler.last_updated())

    def test_turn_on_off(self):
        """Test turn_on and turn_off methods."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        
        # Test turn_on
        handler.turn_on(1)
        self.blnet.turn_on.assert_called_once_with(1, self.node)
        
        # Test turn_off
        handler.turn_off(1)
        self.blnet.turn_off.assert_called_once_with(1, self.node)
        
        # Test turn_auto
        handler.turn_auto(1)
        self.blnet.turn_auto.assert_called_once_with(1, self.node)

    def test_turn_failure_raises(self):
        """Test a failed switch command is reported instead of swallowed."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.blnet.turn_on.side_effect = ConnectionError("Could not log in")
        with self.assertRaises(HomeAssistantError):
            handler.turn_on(1)

    @patch('custom_components.blnet.load_platform')
    def test_failed_fetch_marks_unavailable(self, load_platform):
        """Test a failed fetch marks the handler unavailable until it works again."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.blnet.fetch.side_effect = ConnectionError("Could not get latest data")
        self.assertIsNone(handler.update())
        self.assertFalse(handler.available)
        self.assertIsNone(handler.last_updated())

        self.blnet.fetch.side_effect = None
        self.blnet.fetch.return_value = {
            'analog': {1: {'name': 'T1', 'value': 21.5}},
            'speed': {}, 'power': {}, 'energy': {}, 'digital': {},
        }
        handler.update()
        self.assertTrue(handler.available)
        self.assertEqual(handler.data['blnet analog 1']['value'], 21.5)
        load_platform.assert_called_once()

    @patch('custom_components.blnet.load_platform')
    def test_connects_once_blnet_is_reachable(self, load_platform):
        """Test the client is created on a later update if it failed at startup."""
        connector = Mock()
        connector.connect.side_effect = [TimeoutError("timed out"), self.blnet]
        self.blnet.fetch.return_value = {
            'analog': {}, 'speed': {}, 'power': {}, 'energy': {}, 'digital': {},
        }
        handler = BLNETDataHandler(None, self.node, self.hass, self.config, connector)

        self.assertIsNone(handler.update())
        self.assertFalse(handler.available)

        handler.update()
        self.assertTrue(handler.available)
        self.assertIs(handler.blnet, self.blnet)
        self.assertEqual(connector.connect.call_count, 2)

    def test_skips_update_while_fetch_is_running(self):
        """Test a slow fetch is not run twice at the same time on one connection."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        with handler._update_lock:
            self.assertIsNone(handler.update())
        self.blnet.fetch.assert_not_called()

    def test_digital_values_are_bools(self):
        """Test web ("EIN"/"AUS") and direct (1/0) digital values become bools."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        handler._update_digital_sensors({'digital': {
            1: {'name': 'web on', 'mode': 'AUTO', 'value': 'EIN'},
            2: {'name': 'web off', 'mode': 'HAND', 'value': 'AUS'},
            3: {'value': 1},
            4: {'value': 0},
        }})
        self.assertIs(handler.data['blnet digital 1']['value'], True)
        self.assertIs(handler.data['blnet digital 2']['value'], False)
        self.assertIs(handler.data['blnet digital 3']['value'], True)
        self.assertIs(handler.data['blnet digital 4']['value'], False)


class TestBLNETConnector(unittest.TestCase):
    """Test the BLNETConnector class."""

    def test_init(self):
        """Test initialization of connector."""
        connector = BLNETConnector(
            resource='http://example.com',
            password='test',
            web_port=80,
            ta_port=40000,
            use_web=True,
            use_ta=False
        )
        self.assertEqual(connector.resource, 'http://example.com')
        self.assertEqual(connector.password, 'test')
        self.assertEqual(connector.web_port, 80)
        self.assertEqual(connector.ta_port, 40000)
        self.assertTrue(connector.use_web)
        self.assertFalse(connector.use_ta)

    @patch('pyblnet.BLNET')
    def test_connect(self, mock_blnet):
        """Test connect method."""
        connector = BLNETConnector(
            resource='http://example.com',
            password='test'
        )
        connector.connect()
        mock_blnet.assert_called_once_with(
            'http://example.com',
            password='test',
            web_port=80,
            ta_port=40000,
            use_web=True,
            use_ta=False
        )


if __name__ == '__main__':
    unittest.main() 
