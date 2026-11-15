"""Tests for BLNET sensors."""
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.blnet.const import CONF_USE_WEB


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("entity_id", "state", "device_class", "state_class", "unit"),
    [
        ("sensor.bl_net_ts6", "52.4", "temperature", "measurement", "°C"),
        ("sensor.bl_net_s16", "120", "volume_flow_rate", "measurement", "L/h"),
        ("sensor.bl_net_power_1", "6.984", "power", "measurement", "kW"),
        ("sensor.bl_net_energy_1", "362850.9", "energy", "total_increasing", "kWh"),
        ("sensor.bl_net_speed_1", "24", None, "measurement", None),
    ],
)
async def test_sensors(hass, mock_blnet, mock_config_entry, entity_id, state, device_class, state_class, unit):
    """Sensors get state, device class, state class and unit from the type."""
    await _setup(hass, mock_config_entry)
    s = hass.states.get(entity_id)
    assert s.state == state
    assert s.attributes.get("device_class") == device_class
    assert s.attributes.get("state_class") == state_class
    assert s.attributes.get("unit_of_measurement") == unit


async def test_unknown_analog_type(hass, mock_blnet, mock_config_entry):
    """An analog input without known type gets no class or unit."""
    mock_blnet.fetch.return_value["analog"][3] = {"value": 5, "type": None}
    await _setup(hass, mock_config_entry)
    s = hass.states.get("sensor.bl_net_analog_3")
    assert s.state == "5"
    assert "device_class" not in s.attributes
    assert "unit_of_measurement" not in s.attributes


async def test_digital_outputs_as_sensors_without_web(hass, mock_blnet, mock_config_entry):
    """Without the web interface, digital outputs are sensors."""
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_USE_WEB: False}
    )
    raw = mock_blnet.fetch.return_value
    for entry in raw["analog"].values():
        entry.pop("name")
    raw["digital"] = {1: {"value": 1}}
    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.bl_net_output_1").state == "True"
    assert hass.states.get("sensor.bl_net_analog_6").state == "52.4"


async def test_new_input_added_later(hass, mock_blnet, mock_config_entry, freezer: FrozenDateTimeFactory):
    """An input that appears in a later update gets an entity."""
    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.bl_net_analog_7") is None
    mock_blnet.fetch.return_value["analog"][7] = {"value": 28.9, "type": "temperature"}
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_analog_7").state == "28.9"


async def test_missing_input_unavailable(hass, mock_blnet, mock_config_entry, freezer: FrozenDateTimeFactory):
    """An input that disappears (no sensor / broken wire) is unavailable, not stale."""
    await _setup(hass, mock_config_entry)
    del mock_blnet.fetch.return_value["analog"][6]
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_ts6").state == STATE_UNAVAILABLE
