# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom component (`custom_components/blnet`, distributed via HACS) that integrates the Technische Alternative UVR1611 heating controller through a BL-NET gateway. All device communication is delegated to the [pyblnet](https://github.com/dereisele/pyblnet) library; this repo only maps pyblnet's data onto HA entities.

## Commands

Dependencies are managed with uv (`pyproject.toml`, `uv.lock`; `.python-version` pins 3.14 locally). Tests use `unittest` (not pytest) and must be run from the repo root so `custom_components.blnet` is importable:

```bash
uv sync                  # install pyblnet, homeassistant and ruff into .venv
uv run ruff check        # lint (ruff defaults + pyupgrade "UP" rules)
uv run python -m unittest discover -s custom_components/blnet/tests

# Single test
uv run python -m unittest custom_components.blnet.tests.test_switch.TestBLNETModeSwitch.test_hand_mode_is_off
```

CI (`.github/workflows/tests.yml`) runs `uv sync --locked`, ruff and the tests on Python 3.13 and 3.14 (Home Assistant needs >= 3.13.2).

The pyblnet pin exists twice: `requirements` in `manifest.json` (what Home Assistant installs) and `[tool.uv.sources]` in `pyproject.toml` (what dev/CI uses). Change both together and run `uv lock`.

The repo root doubles as a Home Assistant config directory for manual testing: `configuration.yaml` configures the `blnet` domain against a real BL-NET, and `.storage/`, `home-assistant.log*`, `blueprints/` etc. are HA runtime artifacts; all of these are git-ignored. Run HA against it with `uv run hass -c .`.

## Architecture

The integration uses the legacy YAML-based setup (`setup()` + `load_platform` discovery), not config entries / config flow, and everything is synchronous.

- `__init__.py` — validates YAML config (`CONFIG_SCHEMA`), creates a pyblnet `BLNET` client via `BLNETConnector`, and stores a `BLNETDataHandler` in `hass.data["DATA_blnet"]`. `BLNETUpdateHandler` calls `BLNETDataHandler.update()` once at setup and then every `scan_interval` seconds.
- `BLNETDataHandler.update()` calls `blnet.fetch(node)`, which returns a dict keyed by domain (`analog`, `speed`, `power`, `energy`, `digital`) → id → `{name, value, ...}`. It flattens this into `self.data`, keyed by a `blnet_id` string of the form `"blnet <domain> <id>"`, and on first sight of each `blnet_id` triggers `load_platform(...)` with a discovery_info dict (`id`, `blnet_id`, `name`, `domain`, ...). Entities are therefore created dynamically per poll, not at startup. Digital values are normalized to bools in `self.data` (web reports `"EIN"`/`"AUS"`, BLNET direct reports `1`/`0`), so platforms never see the raw strings.
- `sensor.py` — `BLNETComponent` (`SensorEntity`) reads its value from `communication.data[blnet_id]` on `update()`. Used for analog/speed/power/energy, and also for digital outputs when `use_web: false`. Device class, state class, unit and icon come from `SENSOR_TYPES`, keyed by the entry's `type`: the analog input type from pyblnet (`temperature`, `volume_flow`, `radiation`, `digital`, or None) or the domain name for speed/power/energy. Units are Home Assistant's constants, not pyblnet's strings (pyblnet says `l/h`, HA wants `L/h`). Speed is a level 0-30 without unit, not rpm.
- `switch.py` — for each digital output (only when `use_web: true`), creates two entities: `BLNETSwitch` (on/off) and `BLNETModeSwitch` (on = `AUTO`, off = `HAND`). Writes go through `BLNETDataHandler.turn_on/turn_off/turn_auto`, which call pyblnet with the configured CAN node. Toggling the output switch puts it into `HAND` mode on the device.

Access modes: `use_web` (BL-NET web interface, required for switching) and `use_ta` (BL-NET direct/"ta_direct" protocol, documented as not fully working). pyblnet comes from the `dereisele/pyblnet` fork, which is not on PyPI; `manifest.json` pins it to a GitHub release tag (e.g. `git+https://github.com/dereisele/pyblnet@0.13.0`). The fork lives next to this repo at `../pyblnet`.

Fetch errors (`OSError`/`ValueError` from pyblnet) mark the data handler and all entities unavailable instead of raising; failed switch commands raise `HomeAssistantError`.

Unique IDs are derived from `blnet_id` (sensors) or the output id (switches); changing that format orphans existing entities in users' entity registries.
