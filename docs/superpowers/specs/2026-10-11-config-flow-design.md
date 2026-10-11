# UI configuration (config flow) for ha_blnet

## Goal

Configure the BLNET integration in the Home Assistant UI instead of `configuration.yaml`, and move polling to Home Assistant's `DataUpdateCoordinator`.

Hard requirement: **existing entities are kept.** Alexander renamed his entities in the UI according to his hydraulic chart. After the update every entity must keep its entity ID, custom name, area and history.

## How entities are kept

The entity registry finds an entity by `(domain, platform, unique_id)`. When a config entry registers an entity whose triple already exists, `async_get_or_create` only updates `config_entry_id`, `device_id` and the original_* fields; `entity_id`, the user-set `name`, area and history are untouched. So:

- Platform stays `blnet`, domains stay `sensor` and `switch`.
- Unique IDs stay byte-for-byte identical:
  - sensors: `blnet_sensor_blnet <domain> <id>` (e.g. `blnet_sensor_blnet analog 6`), including digital outputs shown as sensors when `use_web: false`
  - output switches: `blnet_switch_<id>`
  - mode switches: `blnet_mode_switch_<id>`
- Default names stay as they are today (no `has_entity_name`, no new fallback names), so entities that were not renamed don't change either.
- Digital outputs in direct-only mode stay sensors.

Known limitation: deleting the config entry removes its entities from the registry, including custom names. Documented in the README.

## Config flow

- **User step** fields: `resource` (URL), `password` (optional), `use_web` (default true), `use_ta` (default false), `web_port` (80), `ta_port` (40000), `can_node` (optional). At least one of `use_web`/`use_ta` must be on.
- Validation: create the pyblnet client and run one `fetch()` in the executor. `OSError`/`ValueError` → error `cannot_connect`; `AssertionError` → `invalid_config`.
- `single_config_entry: true` in the manifest: one BL-NET per Home Assistant, because the unique IDs don't contain a per-device part.
- Title: the host of `resource`.
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
- All entities get one `DeviceInfo` per entry (manufacturer Technische Alternative, name BL-NET).

## Entities

- `CoordinatorEntity` subclasses of the existing sensor and switch classes; state is read from `coordinator.data[blnet_id]` in `_handle_coordinator_update`.
- Each platform adds the entities present in the first data, and registers a coordinator listener that adds entities for keys that appear later (same as today's per-poll discovery).
- Which platform gets digital outputs is decided as today: `switch` when `use_web` is on, otherwise `sensor`.
- Sensor device class / state class / unit mapping (`SENSOR_TYPES`) is unchanged.

## Removed

`setup()`, `load_platform` discovery, `BLNETUpdateHandler`, the update lock, `setup_platform` in both platforms.

## Translations

`strings.json` and `translations/en.json` for the config flow, options flow, errors, aborts and the repair issue. German (`translations/de.json`) as well, since the integration targets TA users.

## Testing

- Dev dependency `pytest-homeassistant-custom-component`; tests run with pytest and a real Home Assistant test instance, pyblnet mocked.
- New tests: user flow (success, `cannot_connect`, `invalid_config`, both access modes off, single instance), options flow, YAML import (entry created without connecting, issue raised, second import aborts), setup/unload, `ConfigEntryNotReady`, `UpdateFailed` → unavailable → recovery, entities added later, switch commands.
- **Entity preservation test**: pre-populate the entity registry with YAML-era entries (no config entry, custom names), set up the entry, assert same entity IDs and names, now linked to the entry.
- Existing unit tests move to pytest style where they still apply.
- CI runs `uv run pytest`. `pytest-homeassistant-custom-component` pins an exact Home Assistant version (currently 2026.10.1) and needs Python 3.14, so `requires-python` becomes `>=3.14` and CI tests on 3.14 only.
- Manual check before release: run the local config dir (`uv run hass -c .`) once with the YAML block to see the import and the repair issue, and against the real BL-NET.

## Out of scope

Binary sensors for digital outputs in direct-only mode, reauth flow, multiple BL-NETs, diagnostics.
