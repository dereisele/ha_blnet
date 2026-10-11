"""Tests for BLNET diagnostics."""
from homeassistant.components.diagnostics import REDACTED

from custom_components.blnet.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass, mock_blnet, mock_config_entry):
    """The password is redacted, data and options are included."""
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "password": "0128"}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diag["entry"]["data"]["password"] == REDACTED
    assert diag["entry"]["options"] == {"scan_interval": 360}
    assert diag["data"]["blnet analog 6"]["value"] == 52.4
