"""Tests for the BLNET config flow."""
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.blnet.const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def mock_setup_entry():
    """Don't set up the entry in flow tests (standard Home Assistant pattern).

    create=True: before Task 4 the module has the old sync setup() and no
    async_setup_entry; afterwards it has async_setup and async_setup_entry.
    """
    with (
        patch("custom_components.blnet.async_setup_entry", create=True, return_value=True),
        patch("custom_components.blnet.async_setup", create=True, return_value=True),
        patch("custom_components.blnet.setup", create=True, return_value=True),
    ):
        yield


USER_INPUT = {
    CONF_RESOURCE: "http://192.168.100.19",
    CONF_USE_WEB: False,
    CONF_USE_TA: True,
    CONF_WEB_PORT: 80.0,  # NumberSelector returns floats
    CONF_TA_PORT: 40000.0,
}


async def _start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow(hass, mock_blnet):
    """A reachable BL-NET creates the entry with int ports."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.100.19"
    assert result["data"] == {
        CONF_RESOURCE: "http://192.168.100.19",
        CONF_PASSWORD: None,
        CONF_USE_WEB: False,
        CONF_USE_TA: True,
        CONF_WEB_PORT: 80,
        CONF_TA_PORT: 40000,
        CONF_NODE: None,
    }
    assert result["options"] == {CONF_SCAN_INTERVAL: 360}


async def test_user_flow_bare_ip_title(hass, mock_blnet):
    """An address without scheme is used as title as is."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_RESOURCE: "192.168.100.19"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.100.19"


async def test_user_flow_with_node_and_password(hass, mock_blnet):
    """Optional CAN node and password are stored."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_NODE: 20.0, CONF_PASSWORD: "0128"}
    )
    assert result["data"][CONF_NODE] == 20
    assert result["data"][CONF_PASSWORD] == "0128"
    mock_blnet.fetch.assert_called_once_with(20)


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (TimeoutError("timed out"), "cannot_connect"),
        (ValueError("No BLNET found"), "cannot_connect"),
        (AssertionError(), "invalid_config"),
    ],
)
async def test_user_flow_errors(hass, mock_blnet, side_effect, error):
    """Errors are shown and the user can retry."""
    result = await _start(hass)
    with patch("custom_components.blnet.coordinator.BLNET", side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_access_mode(hass, mock_blnet):
    """Web interface and direct access can't both be off."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_USE_WEB: False, CONF_USE_TA: False}
    )
    assert result["errors"] == {"base": "no_access_mode"}
    mock_blnet.fetch.assert_not_called()


async def test_user_flow_no_data(hass, mock_blnet):
    """A connection that returns no values (e.g. wrong password) is rejected."""
    mock_blnet.fetch.return_value = {
        "analog": {}, "digital": {}, "speed": {}, "power": {}, "energy": {},
    }
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_data"}


async def test_single_instance(hass, mock_blnet, mock_config_entry):
    """Only one BL-NET can be configured."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_import(hass, mock_blnet):
    """YAML is imported without connecting; scan_interval goes to options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_RESOURCE: "http://192.168.100.19",
            CONF_USE_WEB: False,
            CONF_USE_TA: True,
            CONF_WEB_PORT: 80,
            CONF_TA_PORT: 40000,
            CONF_SCAN_INTERVAL: 120,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.100.19"
    assert result["data"][CONF_PASSWORD] is None
    assert result["data"][CONF_NODE] is None
    assert result["options"] == {CONF_SCAN_INTERVAL: 120}
    mock_blnet.fetch.assert_not_called()


async def test_reconfigure(hass, mock_blnet, mock_config_entry):
    """Reconfigure validates and updates the entry."""
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch("custom_components.blnet.coordinator.BLNET", side_effect=OSError("down")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_RESOURCE: "http://192.168.100.20"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_RESOURCE] == "http://192.168.100.20"
    assert mock_config_entry.title == "192.168.100.20"


async def test_options(hass, mock_blnet, mock_config_entry):
    """The scan interval can be changed."""
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_SCAN_INTERVAL: 60}


async def test_import_without_access_mode_aborts(hass, mock_blnet):
    """A YAML config with neither web nor direct access can never work."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_RESOURCE: "http://192.168.100.19", CONF_USE_WEB: False, CONF_USE_TA: False},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_access_mode"
