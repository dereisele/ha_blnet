# UI configuration (config flow) for ha_blnet

## Goal

Configure the BLNET integration in the Home Assistant UI instead of `configuration.yaml`, and move polling to Home Assistant's `DataUpdateCoordinator`.

Follow the Home Assistant developer docs, i.e. the [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist): all Bronze and Silver rules, and the Gold rules that apply. Progress is tracked in `custom_components/blnet/quality_scale.yaml` (`done` / `exempt` with a reason), as core integrations do.

Hard requirement: **existing entities are kept.** Alexander renamed his entities in the UI according to his hydraulic chart. After the update every entity must keep its entity ID, custom name, area and history.

## How entities are kept

The entity registry finds an entity by `(domain, platform, unique_id)`. When a config entry registers an entity whose triple already exists, `async_get_or_create` only updates `config_entry_id`, `device_id` and the original_* fields; `entity_id`, the user-set `name`, area and history are untouched. So:

- Platform stays `blnet`, domains stay `sensor` and `switch`.
- Unique IDs stay byte-for-byte identical:
  - sensors: `blnet_sensor_blnet <domain> <id>` (e.g. `blnet_sensor_blnet analog 6`), including digital outputs shown as sensors when `use_web: false`
  - output switches: `blnet_switch_<id>`
  - mode switches: `blnet_mode_switch_<id>`
- `has_entity_name = True` (Bronze rule). Names set in the UI are stored in the registry and shown as they are, without the device prefix (`async_get_legacy_friendly_name` uses `entry.name` alone when it is set), so renamed entities look exactly the same. Entities that were never renamed get the device name in front, e.g. "BL-NET Analog 6". Entity IDs never change.
- Digital outputs in direct-only mode stay sensors.

Known limitation: deleting the config entry removes its entities from the registry, including custom names. Documented in the README.

## File layout (`common-modules`)

`__init__.py` (setup, YAML import trigger), `const.py`, `config_flow.py`, `coordinator.py`, `entity.py` (shared `BLNETEntity` base with device info), `sensor.py`, `switch.py`, `diagnostics.py`, `strings.json`, `translations/en.json`, `translations/de.json`, `icons.json`, `quality_scale.yaml`.

## Config flow

- **User step** fields: `resource` (URL), `password` (optional), `use_web` (default true), `use_ta` (default false), `web_port` (80), `ta_port` (40000), `can_node` (optional). At least one of `use_web`/`use_ta` must be on.
- Every field has a `data_description`; the form uses selectors.
- Validation (`test-before-configure`): create the pyblnet client and run one `fetch()` in the executor. `OSError`/`ValueError` → error `cannot_connect`; `AssertionError` → `invalid_config`.
- `single_config_entry: true` in the manifest (`unique-config-entry`): one BL-NET per Home Assistant, because the unique IDs don't contain a per-device part.
- Title: the host of `resource`.
- **Reconfigure flow** (`reconfiguration-flow`): change address, ports, password, access modes and CAN node of the existing entry, with the same validation; reloads the entry.
- **Reauth flow**: exempt. pyblnet's web interface returns empty data instead of raising on a failed login, so a wrong password can't be told apart from a network error. The reconfigure flow covers changing the password.
- **Options flow**: `scan_interval` in seconds (default 360, minimum 10). Changing options reloads the entry.

## YAML import

- `async_setup` reads a `blnet:` block (same schema as today) and starts an `import` flow with it once.
- The import step creates the entry **without** a connection test, so an offline BL-NET at startup doesn't lose the config. `scan_interval` goes into the entry's options, everything else into its data.
- If an entry already exists, the import aborts (`single_instance_allowed`), so restarts with YAML still present don't duplicate.
- A repair issue (`deprecated_yaml`, via the issue registry) tells the user to remove the YAML block. It is raised whenever YAML is present.

## Runtime

- `async_setup_entry` creates `BLNETCoordinator(DataUpdateCoordinator)` with `update_interval = scan_interval`, stores it in `entry.runtime_data`, runs `async_config_entry_first_refresh()` and forwards the `sensor` and `switch` platforms.
- `_async_update_data` runs in the executor: connect lazily if there is no client yet, `fetch(node)`, then normalise the data into the existing `"blnet <domain> <id>"` → `{value, type, friendly_name, mode}` dict (digital values to bool, as today).
- pyblnet `OSError`/`ValueError` → `UpdateFailed`. Entities become unavailable and recover on the next successful update; the client is kept (pyblnet ≥ 0.11.1 reconnects by itself). A failed first refresh raises `ConfigEntryNotReady` and Home Assistant retries setup with backoff.
- The coordinator serialises updates, so the threading lock and the own timer go away.
- Switch commands (`turn_on`/`turn_off`/`turn_auto`) run in the executor and raise `HomeAssistantError` on failure. On success the entity shows the new state optimistically and calls `coordinator.async_request_refresh()`.
- All entities get one `DeviceInfo` per entry (manufacturer Technische Alternative, name BL-NET) (`devices`).
- `UpdateFailed`, `ConfigEntryNotReady` and the switch `HomeAssistantError` use `translation_domain`/`translation_key` (`exception-translations`).
- Logging when the BL-NET becomes unavailable and comes back is done once each by the coordinator (`log-when-unavailable`).
- `PARALLEL_UPDATES = 0` in `sensor.py` (coordinator polls), `1` in `switch.py` (one command at a time to the web interface) (`parallel-updates`).
- `async_unload_entry` unloads the platforms (`config-entry-unloading`).
- Diagnostics (`diagnostics`): entry data with the password redacted, options, and the last coordinator data.

## Entities

- `CoordinatorEntity` subclasses of the existing sensor and switch classes; state is read from `coordinator.data[blnet_id]` in `_handle_coordinator_update`.
- Each platform adds the entities present in the first data, and registers a coordinator listener that adds entities for keys that appear later (same as today's per-poll discovery).
- Which platform gets digital outputs is decided as today: `switch` when `use_web` is on, otherwise `sensor`.
- Sensor device class / state class / unit mapping (`SENSOR_TYPES`) is unchanged (`entity-device-class`).
- Names (`entity-translations`): with the web interface, the input names configured on the UVR are used as entity names. Without it (direct only) names come from translation keys with the number as placeholder: "Analog {id}", "Speed {id}", "Power {id}", "Energy {id}", "Output {id}", mode switch "Output {id} automatic" / "{name} automatic".
- Icons (`icon-translations`): `icons.json` instead of `icon` properties, with state icons for the switches (output `mdi:flash` / `mdi:flash-off`, mode `mdi:cog` / `mdi:cog-off`) and `mdi:speedometer` for speed.
- Mode switches get `EntityCategory.CONFIG` (`entity-category`). Nothing is disabled by default: every input on the UVR is wired on purpose.
- An entity is available only if the last update succeeded **and** its key is in that update's data. The data dict is rebuilt on every update, never merged into the previous one. pyblnet ≥ 0.13.0 leaves out inputs reading 409.5 °C (no sensor or broken wire), so such an entity goes unavailable instead of showing its last value forever (today's code keeps stale values; verified).
- Entities for inputs that no longer appear (Alexander's analog 1-5 and 15) stay registered and unavailable; the user can delete them. They are not removed automatically.

## Removed

`setup()`, `load_platform` discovery, `BLNETUpdateHandler`, the update lock, `setup_platform` in both platforms.

## Repair issue and translations

`strings.json` and `translations/en.json` for the config flow, options flow, errors, aborts and the repair issue. German (`translations/de.json`) as well, since the integration targets TA users.

## Testing

- Dev dependency `pytest-homeassistant-custom-component`; tests run with pytest and a real Home Assistant test instance, pyblnet mocked.
- Stale value test: an input that disappears from `fetch()` makes its entity unavailable.
- New tests: user flow (success, `cannot_connect`, `invalid_config`, both access modes off, single instance), options flow, YAML import (entry created without connecting, issue raised, second import aborts), setup/unload, `ConfigEntryNotReady`, `UpdateFailed` → unavailable → recovery, entities added later, switch commands.
- **Entity preservation test**: pre-populate the entity registry with YAML-era entries (no config entry, custom names), set up the entry, assert same entity IDs and names, now linked to the entry.
- Existing unit tests move to pytest style where they still apply.
- Coverage above 95 % for every module (`test-coverage`), measured in CI with `pytest-cov`.
- CI runs `uv run pytest`. `pytest-homeassistant-custom-component` pins an exact Home Assistant version (currently 2026.10.1) and needs Python 3.14, so `requires-python` becomes `>=3.14` and CI tests on 3.14 only.
- Manual check before release: run the local config dir (`uv run hass -c .`) once with the YAML block to see the import and the repair issue, and against the real BL-NET.

## Documentation (README)

Sections required by the docs rules: high-level description, supported devices (UVR1611 via BL-NET; DL and CAN modes), installation (HACS) and setup in the UI, configuration and option parameters, how data is updated (polling, default 360 s), supported functions (entities per platform), automation example, use cases, known limitations (one BL-NET, web vs. direct, no reauth, deleting the entry removes custom names), troubleshooting (unavailable entities, debug logging), removal. Also the YAML migration.

## Quality scale status

Exempt, with reason in `quality_scale.yaml`:
- `action-setup`, `docs-actions`, `docs-triggers`, `docs-conditions`: no service actions, triggers or conditions.
- `reauthentication-flow`: see above.
- `discovery`, `discovery-update-info`: the BL-NET has no discovery protocol (no mDNS/SSDP/DHCP signature known).
- `stale-devices`: exactly one device per entry.
- `brands`: custom integration; brand assets are a separate PR to home-assistant/brands, not part of this change.
- Platinum: `async-dependency`, `inject-websession` (pyblnet is synchronous and uses `requests`), `strict-typing` (not attempted now).

## Out of scope

Binary sensors for digital outputs in direct-only mode, multiple BL-NETs, brand assets, Platinum rules.
