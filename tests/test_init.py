"""Tests for setting up the BLNET integration."""
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.blnet.const import DOMAIN

YAML = {
    DOMAIN: {
        "resource": "http://192.168.100.19",
        "use_ta": True,
        "use_web": False,
        "scan_interval": 120,
    }
}


async def test_setup_and_unload(hass, mock_blnet, mock_config_entry):
    """The entry sets up, creates entities and unloads."""
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.bl_net_ts6").state == "52.4"
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry(hass, mock_blnet, mock_config_entry):
    """An unreachable BL-NET at startup means retry later."""
    mock_blnet.fetch.side_effect = TimeoutError("timed out")
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_and_recovery(
    hass, mock_blnet, mock_config_entry, freezer: FrozenDateTimeFactory
):
    """A failed update makes entities unavailable until the next good one."""
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    mock_blnet.fetch.side_effect = ConnectionError("Could not get latest data")
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_ts6").state == STATE_UNAVAILABLE
    mock_blnet.fetch.side_effect = None
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_ts6").state == "52.4"


async def test_options_change_interval(hass, mock_blnet, mock_config_entry):
    """Changing the scan interval reloads with the new interval."""
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 60})
    await hass.async_block_till_done()
    assert mock_config_entry.runtime_data.update_interval == timedelta(seconds=60)


async def test_yaml_import_runs_once(hass, mock_blnet):
    """YAML is imported into one entry and a repair issue is raised."""
    assert await async_setup_component(hass, DOMAIN, YAML)
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].options == {CONF_SCAN_INTERVAL: 120}
    assert ir.async_get(hass).async_get_issue(DOMAIN, "deprecated_yaml") is not None

    # Restart with the YAML still present: no second entry
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data=dict(YAML[DOMAIN])
    )
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_yaml_entities_are_kept(hass, mock_blnet, mock_config_entry):
    """Entities from the YAML setup keep entity ID and user-set name."""
    registry = er.async_get(hass)
    old = registry.async_get_or_create("sensor", DOMAIN, "blnet_sensor_blnet analog 6")
    registry.async_update_entity(old.entity_id, name="TS6 Speicher unten")
    old_speed = registry.async_get_or_create("sensor", DOMAIN, "blnet_sensor_blnet speed 1")

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    new = registry.async_get(old.entity_id)
    assert new.config_entry_id == mock_config_entry.entry_id
    assert new.name == "TS6 Speicher unten"
    assert registry.async_get(old_speed.entity_id).config_entry_id == mock_config_entry.entry_id
    state = hass.states.get(old.entity_id)
    assert state.state == "52.4"
    assert state.attributes["friendly_name"] == "TS6 Speicher unten"
    # No duplicates were created for the existing unique IDs
    ids = [e.unique_id for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)]
    assert len(ids) == len(set(ids))


async def test_empty_first_fetch_retries(hass, mock_blnet, mock_config_entry):
    """A web login that silently returns nothing means retry later."""
    mock_blnet.fetch.return_value = {
        "analog": {}, "digital": {}, "speed": {}, "power": {}, "energy": {},
    }
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_yaml_switches_are_kept(hass, mock_blnet, mock_config_entry):
    """Switches from the YAML setup keep entity ID and user-set name."""
    registry = er.async_get(hass)
    olds = {}
    for uid in ("blnet_switch_1", "blnet_mode_switch_1"):
        old = registry.async_get_or_create("switch", DOMAIN, uid)
        registry.async_update_entity(old.entity_id, name=f"Mein {uid}")
        olds[uid] = old.entity_id

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    for uid, entity_id in olds.items():
        new = registry.async_get(entity_id)
        assert new.unique_id == uid
        assert new.name == f"Mein {uid}"
        assert new.config_entry_id == mock_config_entry.entry_id
    ids = [e.unique_id for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)]
    assert len(ids) == len(set(ids))


async def test_device_configuration_url(hass, mock_blnet, mock_config_entry):
    """The device links to the BL-NET web page, with a scheme if missing."""
    from homeassistant.helpers import device_registry as dr

    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "resource": "192.168.100.19"}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, mock_config_entry.entry_id), mock_config_entry.entry_id
    )
    assert device.configuration_url == "http://192.168.100.19"
