"""Tests for BLNET switches."""
import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.blnet.const import CONF_USE_WEB


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(hass, service, entity_id):
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def test_switch_states(hass, mock_blnet, mock_config_entry):
    """Output and mode switches reflect value and AUTO/HAND."""
    await _setup(hass, mock_config_entry)
    assert hass.states.get("switch.bl_net_pumpe_hk1").state == "on"
    assert hass.states.get("switch.bl_net_pumpe_hk1").attributes["mode"] == "AUTO"
    assert hass.states.get("switch.bl_net_pumpe_hk1_automatic").state == "on"
    assert hass.states.get("switch.bl_net_ladepumpe").state == "off"
    assert hass.states.get("switch.bl_net_ladepumpe_automatic").state == "off"


async def test_unique_ids_and_category(hass, mock_blnet, mock_config_entry):
    """Unique IDs are unchanged from the YAML setup; mode switches are config."""
    await _setup(hass, mock_config_entry)
    registry = er.async_get(hass)
    output = registry.async_get("switch.bl_net_pumpe_hk1")
    mode = registry.async_get("switch.bl_net_pumpe_hk1_automatic")
    assert output.unique_id == "blnet_switch_1"
    assert mode.unique_id == "blnet_mode_switch_1"
    assert mode.entity_category == "config"


async def test_turn_on_off(hass, mock_blnet, mock_config_entry):
    """Turning the output switch sends EIN/AUS and refreshes."""
    await _setup(hass, mock_config_entry)
    await _call(hass, SERVICE_TURN_OFF, "switch.bl_net_pumpe_hk1")
    mock_blnet.turn_off.assert_called_once_with(1, None)
    await _call(hass, SERVICE_TURN_ON, "switch.bl_net_ladepumpe")
    mock_blnet.turn_on.assert_called_once_with(2, None)


async def test_mode_switch(hass, mock_blnet, mock_config_entry):
    """On = AUTO; off = HAND keeping the current output value."""
    await _setup(hass, mock_config_entry)
    await _call(hass, SERVICE_TURN_ON, "switch.bl_net_ladepumpe_automatic")
    mock_blnet.turn_auto.assert_called_once_with(2, None)
    await _call(hass, SERVICE_TURN_OFF, "switch.bl_net_pumpe_hk1_automatic")
    # Output 1 is on, so HAND keeps it on
    mock_blnet.turn_on.assert_called_once_with(1, None)


async def test_switch_command_failure(hass, mock_blnet, mock_config_entry):
    """A failed command raises and keeps the shown state."""
    await _setup(hass, mock_config_entry)
    mock_blnet.turn_off.side_effect = ConnectionError("Could not log in")
    with pytest.raises(HomeAssistantError) as exc:
        await _call(hass, SERVICE_TURN_OFF, "switch.bl_net_pumpe_hk1")
    assert exc.value.translation_key == "command_failed"
    assert hass.states.get("switch.bl_net_pumpe_hk1").state == "on"


async def test_refresh_after_command(hass, mock_blnet, mock_config_entry):
    """A successful command fetches fresh data, so the device state is shown."""
    await _setup(hass, mock_config_entry)
    assert mock_blnet.fetch.call_count == 1
    mock_blnet.fetch.return_value["digital"][1]["value"] = "AUS"
    await _call(hass, SERVICE_TURN_OFF, "switch.bl_net_pumpe_hk1")
    await hass.async_block_till_done()
    assert mock_blnet.fetch.call_count == 2
    assert hass.states.get("switch.bl_net_pumpe_hk1").state == "off"


async def test_no_switches_without_web(hass, mock_blnet, mock_config_entry):
    """Without the web interface there are no switches."""
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_USE_WEB: False}
    )
    await _setup(hass, mock_config_entry)
    assert hass.states.async_entity_ids(SWITCH_DOMAIN) == []
