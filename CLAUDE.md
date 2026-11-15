# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom component (`custom_components/blnet`, distributed via HACS) that integrates the Technische Alternative UVR1611 heating controller through a BL-NET gateway. All device communication is delegated to the [pyblnet](https://github.com/dereisele/pyblnet) library; this repo only maps pyblnet's data onto HA entities.

## Commands

Dependencies are managed with uv (`pyproject.toml`, `uv.lock`; Python >= 3.14.2, Home Assistant 2026.10). Tests use pytest with `pytest-homeassistant-custom-component` and must be run from the repo root so `custom_components.blnet` is importable:

```bash
uv sync                  # install pyblnet, homeassistant, ruff and test deps into .venv
uv run ruff check        # lint (ruff defaults + pyupgrade "UP" rules)
uv run pytest            # all tests in tests/
uv run pytest --cov=custom_components.blnet --cov-fail-under=95   # what CI runs

# Single test
uv run pytest tests/test_switch.py::test_mode_switch
```

CI (`.github/workflows/tests.yml`) runs `uv sync --locked`, ruff and pytest with the 95 % coverage gate on Python 3.14.

The pyblnet pin exists twice: `requirements` in `manifest.json` (what Home Assistant installs) and `[tool.uv.sources]` in `pyproject.toml` (what dev/CI uses). Change both together and run `uv lock`.

The repo root doubles as a Home Assistant config directory for manual testing: `.storage/`, `home-assistant.log*`, `blueprints/` etc. are HA runtime artifacts and git-ignored. Run HA against it with `uv run hass -c .`.

## Architecture

Config-entry based (UI config flow, `single_config_entry`), with a `DataUpdateCoordinator`. pyblnet itself is synchronous, so calls run in the executor. A `blnet:` YAML block is only imported once into a config entry (plus a `deprecated_yaml` repair issue).

- `__init__.py` — YAML import trigger, `async_setup_entry` (coordinator in `entry.runtime_data`, first refresh, platform forwarding), unload.
- `config_flow.py` — user, reconfigure, import and options flow. Entry **data**: connection settings (`resource`, `password`, `use_web`, `use_ta`, `web_port`, `ta_port`, `can_node`). Entry **options**: `scan_interval` (default 360 s, min 10).
- `coordinator.py` — `BLNETCoordinator` calls `blnet.fetch(node)` and rebuilds `data` on every update as `"blnet <domain> <id>" -> {id, domain, name, value, type, mode}` (domains `analog`, `speed`, `power`, `energy`, `digital`; digital values normalised to bool). Fetch errors raise `UpdateFailed`; switch commands go through it and refresh afterwards.
- `entity.py` — `BLNETEntity` base (one device per entry). `sensor.py` — sensors for analog/speed/power/energy and for digital outputs when `use_web` is off. `switch.py` — per digital output an on/off switch and a mode switch (on = `AUTO`, off = `HAND`); entities for outputs appearing later are added dynamically.
- `diagnostics.py`, `icons.json`, `translations/{en,de}.json` (keep keys in sync, `tests/test_translations.py` checks it).
- `quality_scale.yaml` — Integration Quality Scale status per rule; keep it current when behaviour changes.

Access modes: `use_web` (web interface, required for switching) and `use_ta` (BLNET direct; speed, power, energy). pyblnet comes from the `dereisele/pyblnet` fork (not on PyPI), pinned to a GitHub release tag in `manifest.json`; the fork lives next to this repo at `../pyblnet`.

Invariants: unique IDs must never change, or users' existing entities (with renamed names/IDs) are orphaned. Formats: sensors `blnet_sensor_blnet <domain> <id>`, output switches `blnet_switch_<id>`, mode switches `blnet_mode_switch_<id>`.
