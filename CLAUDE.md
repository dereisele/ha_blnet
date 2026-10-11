# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom component (`custom_components/blnet`, distributed via HACS) that integrates the Technische Alternative UVR1611 heating controller through a BL-NET gateway. All device communication is delegated to the [pyblnet](https://github.com/nielstron/pyblnet) library; this repo only maps pyblnet's data onto HA entities.

## Commands

Tests use `unittest` (not pytest) and must be run from the repo root so `custom_components.blnet` is importable:

```bash
# Full suite (same as CI in .github/workflows/tests.yml)
python -m unittest discover -s custom_components/blnet/tests

# Single test
python -m unittest custom_components.blnet.tests.test_sensor.TestBLNETDataHandler.test_init

# Install integration requirements from the manifest (what CI does)
python requirements_from_manifest.py custom_components/blnet/manifest.json > requirements.txt
pip install -r requirements.txt
```

CI uses Python 3.11 and installs `homeassistant` + `fire` alongside the manifest requirements. A local venv is in `.venv/` (contains `hass`).

The repo root doubles as a Home Assistant config directory for manual testing: `configuration.yaml` configures the `blnet` domain against a real BL-NET, and `.storage/`, `home-assistant.log*`, `blueprints/` etc. are HA runtime artifacts; all of these are git-ignored. Run HA against it with `hass -c .`.

## Architecture

The integration uses the legacy YAML-based setup (`setup()` + `load_platform` discovery), not config entries / config flow, and everything is synchronous.

- `__init__.py` — validates YAML config (`CONFIG_SCHEMA`), creates a pyblnet `BLNET` client via `BLNETConnector`, and stores a `BLNETDataHandler` in `hass.data["DATA_blnet"]`. `BLNETUpdateHandler` calls `BLNETDataHandler.update()` once at setup and then every `scan_interval` seconds.
- `BLNETDataHandler.update()` calls `blnet.fetch(node)`, which returns a dict keyed by domain (`analog`, `speed`, `power`, `energy`, `digital`) → id → `{name, value, ...}`. It flattens this into `self.data`, keyed by a `blnet_id` string of the form `"blnet <domain> <id>"`, and on first sight of each `blnet_id` triggers `load_platform(...)` with a discovery_info dict (`id`, `blnet_id`, `name`, `domain`, ...). Entities are therefore created dynamically per poll, not at startup. Digital values are normalized to bools in `self.data` (web reports `"EIN"`/`"AUS"`, BLNET direct reports `1`/`0`), so platforms never see the raw strings.
- `sensor.py` — `BLNETComponent` entities read their values from `communication.data[blnet_id]` on `update()`. Used for analog/speed/power/energy, and also for digital outputs when `use_web: false`.
- `switch.py` — for each digital output (only when `use_web: true`), creates two entities: `BLNETSwitch` (on/off) and `BLNETModeSwitch` (on = `AUTO`, off = `HAND`). Writes go through `BLNETDataHandler.turn_on/turn_off/turn_auto`, which call pyblnet with the configured CAN node. Toggling the output switch puts it into `HAND` mode on the device.

Access modes: `use_web` (BL-NET web interface, required for switching) and `use_ta` (BL-NET direct/"ta_direct" protocol, documented as not fully working). pyblnet comes from the `dereisele/pyblnet` fork, which is not on PyPI; `manifest.json` pins it to a GitHub release tag (e.g. `git+https://github.com/dereisele/pyblnet@0.11.0`). The fork lives next to this repo at `../pyblnet`.

Unique IDs are derived from `blnet_id` (sensors) or the output id (switches); changing that format orphans existing entities in users' entity registries.
