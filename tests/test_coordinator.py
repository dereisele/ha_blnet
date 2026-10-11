"""Tests for the BLNET coordinator."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.blnet.coordinator import BLNETCoordinator, normalize


def test_normalize():
    """Digital values become bools, types are set per domain."""
    raw = {
        "analog": {6: {"name": "TS6", "value": 52.4, "type": "temperature"}},
        "digital": {
            1: {"name": "P1", "mode": "AUTO", "value": "EIN"},
            2: {"name": "P2", "mode": "HAND", "value": "AUS"},
            3: {"value": 1},
            4: {"value": 0},
        },
        "speed": {1: {"value": 24}},
        "power": {},
        "energy": {1: {"value": 1.5}},
    }
    data = normalize(raw)
    assert data["blnet analog 6"] == {
        "id": 6, "domain": "analog", "name": "TS6", "value": 52.4,
        "type": "temperature", "mode": None,
    }
    assert data["blnet speed 1"]["type"] == "speed"
    assert data["blnet energy 1"]["type"] == "energy"
    assert [data[f"blnet digital {i}"]["value"] for i in (1, 2, 3, 4)] == [
        True, False, True, False,
    ]
    assert data["blnet digital 1"]["mode"] == "AUTO"
    assert data["blnet digital 1"]["type"] is None


async def test_update(hass, mock_blnet, mock_config_entry):
    """Data is fetched with the CAN node and normalised."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    assert coordinator.update_interval == timedelta(seconds=360)
    data = await coordinator._async_update_data()
    mock_blnet.fetch.assert_called_once_with(None)
    assert data["blnet analog 6"]["value"] == 52.4


async def test_update_uses_can_node(hass, mock_blnet, mock_config_entry):
    """The configured CAN node is passed to fetch()."""
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "can_node": 20}
    )
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    mock_blnet.fetch.assert_called_once_with(20)


async def test_empty_fetch_gives_empty_data(hass, mock_blnet, mock_config_entry):
    """A failed web login (empty dicts from pyblnet) gives no entity data."""
    mock_blnet.fetch.return_value = {
        "analog": {}, "digital": {}, "speed": {}, "power": {}, "energy": {},
    }
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    assert await coordinator._async_update_data() == {}


@pytest.mark.parametrize("error", [TimeoutError("timed out"), ConnectionError("x"), ValueError("x")])
async def test_update_failed(hass, mock_blnet, mock_config_entry, error):
    """pyblnet errors become UpdateFailed, the client is kept."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    mock_blnet.fetch.side_effect = error
    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.translation_key == "cannot_connect"
    assert coordinator.client is mock_blnet


async def test_connect_failure_retried(hass, mock_blnet, mock_config_entry):
    """If creating the client fails, the next update tries again."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    with patch(
        "custom_components.blnet.coordinator.BLNET", side_effect=OSError("down")
    ), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.client is None
    await coordinator._async_update_data()
    assert coordinator.client is mock_blnet


@pytest.mark.parametrize(("state", "method"), [("on", "turn_on"), ("off", "turn_off"), ("auto", "turn_auto")])
async def test_set_output(hass, mock_blnet, mock_config_entry, state, method):
    """Commands go to pyblnet with the CAN node."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    await coordinator.async_set_output(1, state)
    getattr(mock_blnet, method).assert_called_once_with(1, None)
    await coordinator.async_shutdown()


async def test_set_output_failure(hass, mock_blnet, mock_config_entry):
    """A failed command raises a translated HomeAssistantError."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    mock_blnet.turn_on.side_effect = ConnectionError("Could not log in")
    with pytest.raises(HomeAssistantError) as exc:
        await coordinator.async_set_output(1, "on")
    assert exc.value.translation_key == "command_failed"
