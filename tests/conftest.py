"""Fixtures for BLNET tests."""

import copy
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blnet.const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DOMAIN,
)

ENTRY_DATA = {
    CONF_RESOURCE: "http://192.168.100.19",
    CONF_PASSWORD: None,
    CONF_USE_WEB: True,
    CONF_USE_TA: True,
    CONF_WEB_PORT: 80,
    CONF_TA_PORT: 40000,
    CONF_NODE: None,
}

# What pyblnet 0.13.0 BLNET.fetch() returns with web interface and direct access
RAW_DATA = {
    "analog": {
        6: {"id": "6", "name": "TS6", "value": 52.4, "type": "temperature",
            "unit_of_measurement": "°C"},
        16: {"id": "16", "name": "S16", "value": 120, "type": "volume_flow",
             "unit_of_measurement": "l/h"},
    },
    "digital": {
        1: {"id": "1", "name": "Pumpe HK1", "mode": "AUTO", "value": "EIN"},
        2: {"id": "2", "name": "Ladepumpe", "mode": "HAND", "value": "AUS"},
    },
    "speed": {1: {"value": 24, "unit_of_measurement": None}},
    "power": {1: {"value": 6.984, "unit_of_measurement": "kW"}},
    "energy": {1: {"value": 362850.9, "unit_of_measurement": "kWh"}},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Load custom_components/blnet in every test that uses hass.

    Only requested for hass tests, so plain (and legacy unittest) tests work.
    """
    if "hass" in request.fixturenames:
        request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def mock_blnet():
    """Mock the pyblnet client created by the integration."""
    with patch("custom_components.blnet.coordinator.BLNET", autospec=True) as cls:
        client = cls.return_value
        client.fetch.return_value = copy.deepcopy(RAW_DATA)
        yield client


@pytest.fixture
def mock_config_entry(hass):
    """A BLNET config entry added to hass (not set up)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.168.100.19",
        data=dict(ENTRY_DATA),
        options={CONF_SCAN_INTERVAL: 360},
    )
    entry.add_to_hass(hass)
    return entry
