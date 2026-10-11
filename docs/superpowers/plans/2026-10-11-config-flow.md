# UI Configuration (Config Flow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the BLNET integration in the Home Assistant UI (config flow with YAML import), poll with a `DataUpdateCoordinator`, and follow the Integration Quality Scale (Bronze, Silver, applicable Gold) while keeping every existing entity.

**Architecture:** A config entry holds connection data (`entry.data`) and the scan interval (`entry.options`). `BLNETCoordinator` owns the synchronous pyblnet client, runs `fetch()` in the executor and rebuilds a flat dict `"blnet <domain> <id>" -> {...}` on every update. Sensor and switch platforms create `CoordinatorEntity` subclasses with the same unique IDs as today and add entities for keys that appear later.

**Tech Stack:** Python 3.14, Home Assistant 2026.10.1, pyblnet 0.13.0 (git tag), uv, pytest + pytest-homeassistant-custom-component, ruff.

**Spec:** `docs/superpowers/specs/2026-10-11-config-flow-design.md`

## Global Constraints

- Platform stays `blnet`; domains stay `sensor` and `switch`.
- Unique IDs byte-for-byte as today: sensors `blnet_sensor_blnet <domain> <id>` (e.g. `blnet_sensor_blnet analog 6`, digital-as-sensor `blnet_sensor_blnet digital 1`), output switches `blnet_switch_<id>`, mode switches `blnet_mode_switch_<id>`. `<id>` is the integer key from pyblnet formatted with `str()`.
- Digital outputs are switches when `use_web` is on, sensors otherwise.
- `single_config_entry: true`; YAML is imported once without a connection test; `scan_interval` lives in `entry.options` (default 360, minimum 10).
- pyblnet errors to catch are `OSError` and `ValueError` (plus `AssertionError` for invalid parameters in the config flow). Never catch bare `Exception`.
- Translations for custom integrations live in `translations/en.json` and `translations/de.json` (Home Assistant does not read `strings.json` for custom integrations, so there is no `strings.json`).
- `requires-python = ">=3.14"`; CI tests on Python 3.14 only.
- Coverage above 95 % for every module in `custom_components/blnet`.
- Run everything from the repo root `/home/alexander/develop/privat/ha_blnet`. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Web-only with a wrong password: pyblnet's web interface returns empty dicts instead of raising, so the flow must report `no_data` and the coordinator must leave all entities unavailable, not show zeros. Tests: Task 2 (`test_empty_fetch_gives_empty_data`), Task 3 (`test_user_flow_no_data`).
2. Switch command while the BL-NET is unreachable: must raise a translated `HomeAssistantError` and leave the shown state unchanged. Test: Task 5 (`test_switch_command_failure`).
3. Address without scheme (`192.168.100.19`): entry title must still be the host and no crash. Test: Task 3 (`test_user_flow_bare_ip_title`).
4. Restart with the YAML block still present after the import: no second entry, issue still raised. Test: Task 4 (`test_yaml_import_runs_once`).
5. Input that disappears from `fetch()` (no sensor / broken wire): entity unavailable, not stale. Test: Task 4 (`test_missing_input_unavailable`).

---

## File Structure

| File | Responsibility |
|---|---|
| `custom_components/blnet/const.py` | Domain, config keys, defaults, sensor domains |
| `custom_components/blnet/coordinator.py` | pyblnet client creation, data normalisation, `BLNETCoordinator`, switch commands |
| `custom_components/blnet/config_flow.py` | User, import, reconfigure and options flows |
| `custom_components/blnet/__init__.py` | YAML schema, import trigger + repair issue, entry setup/unload |
| `custom_components/blnet/entity.py` | `BLNETEntity` base: device info, availability, naming |
| `custom_components/blnet/sensor.py` | Sensor platform, `SENSOR_TYPES` mapping |
| `custom_components/blnet/switch.py` | Output and mode switches |
| `custom_components/blnet/diagnostics.py` | Config entry diagnostics |
| `custom_components/blnet/icons.json` | Icon translations |
| `custom_components/blnet/translations/{en,de}.json` | All UI strings |
| `custom_components/blnet/quality_scale.yaml` | Rule status |
| `tests/` | pytest tests (moved out of the integration folder) |

---

### Task 1: Test tooling on pytest-homeassistant-custom-component

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/tests.yml`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Move: `custom_components/blnet/tests/test_sensor.py` → `tests/test_legacy_sensor.py`, `custom_components/blnet/tests/test_switch.py` → `tests/test_legacy_switch.py` (deleted in Task 5)
- Delete: `custom_components/blnet/tests/`

**Interfaces:**
- Produces: fixtures `mock_blnet` (the mocked pyblnet client instance; `mock_blnet.fetch.return_value` is a deep copy of `RAW_DATA`), `RAW_DATA` constant, `ENTRY_DATA` constant, `mock_config_entry` (a `MockConfigEntry` added to hass, not set up). Used by every later task.

- [ ] **Step 1: Update pyproject.toml**

Replace `requires-python`, the dev group and add pytest config:

```toml
requires-python = ">=3.14"
```

```toml
[dependency-groups]
dev = [
    "pytest-cov",
    "pytest-homeassistant-custom-component",
    "ruff",
]
```

(`homeassistant` comes in as a pinned dependency of `pytest-homeassistant-custom-component`.)

Append:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Lock and sync**

Run: `uv lock && uv sync`
Expected: resolves `pytest-homeassistant-custom-component` with `homeassistant==2026.10.1`.

- [ ] **Step 3: Write `tests/__init__.py` (empty, docstring only) and `tests/conftest.py`**

```python
"""Fixtures for BLNET tests."""
import copy
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blnet.const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DOMAIN,
)

ENTRY_DATA = {
    CONF_RESOURCE: "http://192.168.100.19",
    CONF_PASSWORD: None,
    CONF_USE_WEB: True,
    CONF_USE_TA: True,
    CONF_WEB_PORT: 80,
    CONF_TA_PORT: 40000,
    CONF_NODE: None,
}

# What pyblnet 0.13.0 BLNET.fetch() returns with web interface and direct access
RAW_DATA = {
    "analog": {
        6: {"id": "6", "name": "TS6", "value": 52.4, "type": "temperature",
            "unit_of_measurement": "°C"},
        16: {"id": "16", "name": "S16", "value": 120, "type": "volume_flow",
             "unit_of_measurement": "l/h"},
    },
    "digital": {
        1: {"id": "1", "name": "Pumpe HK1", "mode": "AUTO", "value": "EIN"},
        2: {"id": "2", "name": "Ladepumpe", "mode": "HAND", "value": "AUS"},
    },
    "speed": {1: {"value": 24, "unit_of_measurement": None}},
    "power": {1: {"value": 6.984, "unit_of_measurement": "kW"}},
    "energy": {1: {"value": 362850.9, "unit_of_measurement": "kWh"}},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Load custom_components/blnet in every test that uses hass.

    Only requested for hass tests, so plain (and legacy unittest) tests work.
    """
    if "hass" in request.fixturenames:
        request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def mock_blnet():
    """Mock the pyblnet client created by the integration."""
    with patch("custom_components.blnet.coordinator.BLNET", autospec=True) as cls:
        client = cls.return_value
        client.fetch.return_value = copy.deepcopy(RAW_DATA)
        yield client


@pytest.fixture
def mock_config_entry(hass):
    """A BLNET config entry added to hass (not set up)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.168.100.19",
        data=dict(ENTRY_DATA),
        options={CONF_SCAN_INTERVAL: 360},
    )
    entry.add_to_hass(hass)
    return entry
```

`conftest.py` imports `custom_components.blnet.const`, which Task 2 creates. Until then create a minimal `custom_components/blnet/const.py` in this task:

```python
"""Constants for the BLNET integration."""

DOMAIN = "blnet"

CONF_WEB_PORT = "web_port"
CONF_TA_PORT = "ta_port"
CONF_USE_WEB = "use_web"
CONF_USE_TA = "use_ta"
CONF_NODE = "can_node"

DEFAULT_WEB_PORT = 80
DEFAULT_TA_PORT = 40000
DEFAULT_SCAN_INTERVAL = 360
MIN_SCAN_INTERVAL = 10

# Domains of pyblnet's fetch() that are always sensors
SENSOR_DOMAINS = ("analog", "speed", "power", "energy")
```

- [ ] **Step 4: Move the old tests**

```bash
git mv custom_components/blnet/tests/test_sensor.py tests/test_legacy_sensor.py
git mv custom_components/blnet/tests/test_switch.py tests/test_legacy_switch.py
git rm -q custom_components/blnet/tests/__init__.py 2>/dev/null; rm -rf custom_components/blnet/tests
```

- [ ] **Step 5: Run the suite with pytest**

Run: `uv run pytest -q`
Expected: the 27 existing tests pass (they are unittest classes, pytest collects them).

- [ ] **Step 6: Switch CI to pytest on Python 3.14**

`.github/workflows/tests.yml`: matrix `python-version: ["3.14"]`, and replace the test step with:

```yaml
    - name: Run tests
      run: uv run pytest --cov=custom_components.blnet --cov-report=term-missing
```

- [ ] **Step 7: Commit**

```bash
git add -A pyproject.toml uv.lock .github tests custom_components/blnet
git commit -m "Run tests with pytest-homeassistant-custom-component"
```

---

### Task 2: Coordinator

**Files:**
- Modify: `custom_components/blnet/const.py` (already complete from Task 1)
- Create: `custom_components/blnet/coordinator.py`
- Create: `custom_components/blnet/translations/en.json`, `custom_components/blnet/translations/de.json` (exceptions section only; later tasks extend them)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `const.py` names.
- Produces:
  - `type BLNETConfigEntry = ConfigEntry[BLNETCoordinator]`
  - `create_client(data: Mapping[str, Any]) -> BLNET` (blocking)
  - `normalize(raw: dict) -> dict[str, dict[str, Any]]`: keys `"blnet <domain> <id>"`; values `{"id": int, "domain": str, "name": str | None, "value": Any, "type": str | None, "mode": str | None}`; digital values are bool; `type` is the analog input type for `analog`, the domain name for `speed`/`power`/`energy`, `None` for `digital`.
  - `class BLNETCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]])` with `__init__(hass, entry)`, `client: BLNET | None`, `async def async_set_output(output_id: int, state: str) -> None` where state is `"on"`, `"off"` or `"auto"`.
  - Translation keys in `exceptions`: `cannot_connect` (placeholder `error`), `command_failed` (placeholders `output`, `state`).

- [ ] **Step 1: Write the failing tests**

`tests/test_coordinator.py`:

```python
"""Tests for the BLNET coordinator."""
from datetime import timedelta

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
    from unittest.mock import patch

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


async def test_set_output_failure(hass, mock_blnet, mock_config_entry):
    """A failed command raises a translated HomeAssistantError."""
    coordinator = BLNETCoordinator(hass, mock_config_entry)
    await coordinator._async_update_data()
    mock_blnet.turn_on.side_effect = ConnectionError("Could not log in")
    with pytest.raises(HomeAssistantError) as exc:
        await coordinator.async_set_output(1, "on")
    assert exc.value.translation_key == "command_failed"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_coordinator.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'custom_components.blnet.coordinator'`.

- [ ] **Step 3: Implement `custom_components/blnet/coordinator.py`**

```python
"""Data update coordinator for the BLNET integration."""
from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyblnet import BLNET

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
    SENSOR_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)

type BLNETConfigEntry = ConfigEntry[BLNETCoordinator]


def create_client(data: Mapping[str, Any]) -> BLNET:
    """Create the pyblnet client. Blocking: connects in the constructor."""
    return BLNET(
        data[CONF_RESOURCE],
        password=data.get(CONF_PASSWORD),
        web_port=int(data.get(CONF_WEB_PORT, DEFAULT_WEB_PORT)),
        ta_port=int(data.get(CONF_TA_PORT, DEFAULT_TA_PORT)),
        use_web=data.get(CONF_USE_WEB, True),
        use_ta=data.get(CONF_USE_TA, False),
    )


def _digital_to_bool(value: Any) -> bool:
    """The web interface reports "EIN"/"AUS", BLNET direct reports 1/0."""
    if isinstance(value, str):
        return value == "EIN"
    return bool(value)


def normalize(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten pyblnet's fetch() result, keyed like the entity unique IDs."""
    data: dict[str, dict[str, Any]] = {}
    for domain in SENSOR_DOMAINS:
        for key, entry in raw.get(domain, {}).items():
            data[f"{DOMAIN} {domain} {key}"] = {
                "id": key,
                "domain": domain,
                "name": entry.get("name"),
                "value": entry.get("value"),
                # Analog inputs have a type (temperature, volume_flow, ...)
                "type": entry.get("type") if domain == "analog" else domain,
                "mode": None,
            }
    for key, entry in raw.get("digital", {}).items():
        data[f"{DOMAIN} digital {key}"] = {
            "id": key,
            "domain": "digital",
            "name": entry.get("name"),
            "value": _digital_to_bool(entry.get("value")),
            "type": None,
            "mode": entry.get("mode"),
        }
    return data


class BLNETCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch data from the BL-NET."""

    config_entry: BLNETConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BLNETConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client: BLNET | None = None

    @property
    def _node(self) -> int | None:
        return self.config_entry.data.get(CONF_NODE)

    def _fetch(self) -> dict[str, Any]:
        if self.client is None:
            self.client = create_client(self.config_entry.data)
        return self.client.fetch(self._node)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            raw = await self.hass.async_add_executor_job(self._fetch)
        except (OSError, ValueError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        return normalize(raw)

    async def async_set_output(self, output_id: int, state: str) -> None:
        """Set a digital output to "on", "off" or "auto" via the web interface."""
        assert self.client is not None
        turn = {
            "on": self.client.turn_on,
            "off": self.client.turn_off,
            "auto": self.client.turn_auto,
        }[state]
        try:
            await self.hass.async_add_executor_job(turn, output_id, self._node)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"output": str(output_id), "state": state},
            ) from err
        await self.async_request_refresh()
```

`translations/en.json`:

```json
{
  "exceptions": {
    "cannot_connect": {
      "message": "Could not fetch data from the BL-NET: {error}"
    },
    "command_failed": {
      "message": "Could not set BL-NET output {output} to {state}"
    }
  }
}
```

`translations/de.json`:

```json
{
  "exceptions": {
    "cannot_connect": {
      "message": "Daten konnten nicht vom BL-NET abgerufen werden: {error}"
    },
    "command_failed": {
      "message": "BL-NET-Ausgang {output} konnte nicht auf {state} gesetzt werden"
    }
  }
}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_coordinator.py -q && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/blnet/coordinator.py custom_components/blnet/const.py custom_components/blnet/translations tests/test_coordinator.py
git commit -m "Add data update coordinator"
```

---

### Task 3: Config flow (user, import, reconfigure, options)

**Files:**
- Create: `custom_components/blnet/config_flow.py`
- Modify: `custom_components/blnet/manifest.json`
- Modify: `custom_components/blnet/translations/en.json`, `de.json` (add `config`, `options` sections)
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `create_client` from `coordinator.py`; const names.
- Produces: `BLNETConfigFlow` with steps `user`, `import`, `reconfigure`; `BLNETOptionsFlow` step `init`. Error keys: `cannot_connect`, `invalid_config`, `no_access_mode`, `no_data`. Import step expects the validated YAML dict (keys of `ENTRY_DATA` plus optional `scan_interval`).

- [ ] **Step 1: Update manifest**

`custom_components/blnet/manifest.json` (keys after `domain`/`name` alphabetical):

```json
{
  "domain": "blnet",
  "name": "BLNET",
  "codeowners": ["@nielstron", "@dereisele"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/dereisele/ha_blnet/blob/master/README.md",
  "integration_type": "device",
  "iot_class": "local_polling",
  "loggers": ["pyblnet"],
  "requirements": ["pyblnet@git+https://github.com/dereisele/pyblnet@0.13.0"],
  "single_config_entry": true,
  "version": "0.8.0b1"
}
```

(Keep whatever `version` is current.)

- [ ] **Step 2: Write the failing tests**

`tests/test_config_flow.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_config_flow.py -q`
Expected: FAIL (no config flow for `blnet`).

- [ ] **Step 4: Implement `custom_components/blnet/config_flow.py`**

```python
"""Config flow for the BLNET integration."""
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_RESOURCE, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import create_client

PORT_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RESOURCE): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Optional(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_USE_WEB, default=True): BooleanSelector(),
        vol.Required(CONF_USE_TA, default=False): BooleanSelector(),
        vol.Required(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): PORT_SELECTOR,
        vol.Required(CONF_TA_PORT, default=DEFAULT_TA_PORT): PORT_SELECTOR,
        vol.Optional(CONF_NODE): NumberSelector(
            NumberSelectorConfig(min=1, max=62, mode=NumberSelectorMode.BOX)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL, max=86400, unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


def _entry_data(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Entry data from form or YAML input, with ints instead of floats."""
    node = user_input.get(CONF_NODE)
    return {
        CONF_RESOURCE: user_input[CONF_RESOURCE],
        CONF_PASSWORD: user_input.get(CONF_PASSWORD) or None,
        CONF_USE_WEB: user_input.get(CONF_USE_WEB, True),
        CONF_USE_TA: user_input.get(CONF_USE_TA, False),
        CONF_WEB_PORT: int(user_input.get(CONF_WEB_PORT, DEFAULT_WEB_PORT)),
        CONF_TA_PORT: int(user_input.get(CONF_TA_PORT, DEFAULT_TA_PORT)),
        CONF_NODE: None if node is None else int(node),
    }


def _title(data: Mapping[str, Any]) -> str:
    resource = data[CONF_RESOURCE]
    return urlparse(resource).hostname or resource


def _test_connection(data: Mapping[str, Any]) -> bool:
    """Connect and fetch once. Blocking. Return whether any values came back."""
    raw = create_client(data).fetch(data[CONF_NODE])
    return any(raw.get(domain) for domain in raw)


async def _validate(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    if not data[CONF_USE_WEB] and not data[CONF_USE_TA]:
        return {"base": "no_access_mode"}
    try:
        has_data = await hass.async_add_executor_job(_test_connection, data)
    except AssertionError:
        return {"base": "invalid_config"}
    except (OSError, ValueError):
        return {"base": "cannot_connect"}
    if not has_data:
        return {"base": "no_data"}
    return {}


class BLNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for BLNET."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "BLNETOptionsFlow":
        """Return the options flow."""
        return BLNETOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up the BL-NET from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _entry_data(user_input)
            errors = await _validate(self.hass, data)
            if not errors:
                return self.async_create_entry(
                    title=_title(data),
                    data=data,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the YAML configuration without testing the connection."""
        data = _entry_data(import_data)
        return self.async_create_entry(
            title=_title(data),
            data=data,
            options={
                CONF_SCAN_INTERVAL: import_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the connection settings of the existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _entry_data(user_input)
            errors = await _validate(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, title=_title(data), data=data)
        suggested = user_input or {k: v for k, v in entry.data.items() if v is not None}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, suggested),
            errors=errors,
        )


class BLNETOptionsFlow(OptionsFlowWithReload):
    """Options for BLNET; changing them reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the scan interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
```

- [ ] **Step 5: Add config/options strings**

Merge into `translations/en.json` (keep `exceptions`):

```json
  "config": {
    "step": {
      "user": {
        "title": "Connect to the BL-NET",
        "data": {
          "resource": "Address",
          "password": "Password",
          "use_web": "Use web interface",
          "use_ta": "Use BLNET direct",
          "web_port": "Web interface port",
          "ta_port": "BLNET direct port",
          "can_node": "CAN node"
        },
        "data_description": {
          "resource": "Address of the BL-NET, e.g. http://192.168.1.10",
          "password": "Password of the \"Expert\" user of the web interface. Leave empty if none is set.",
          "use_web": "Read names and values from the web interface. Needed for switching outputs.",
          "use_ta": "Read values over the BL-NET's direct TCP connection. Needed for speed, power and energy.",
          "web_port": "Port of the web interface, usually 80",
          "ta_port": "Port of the direct connection, usually 40000",
          "can_node": "CAN node of the controller. Leave empty to keep the node selected on the BL-NET."
        }
      },
      "reconfigure": {
        "title": "Change BL-NET connection",
        "data": {
          "resource": "Address",
          "password": "Password",
          "use_web": "Use web interface",
          "use_ta": "Use BLNET direct",
          "web_port": "Web interface port",
          "ta_port": "BLNET direct port",
          "can_node": "CAN node"
        },
        "data_description": {
          "resource": "Address of the BL-NET, e.g. http://192.168.1.10",
          "password": "Password of the \"Expert\" user of the web interface. Leave empty if none is set.",
          "use_web": "Read names and values from the web interface. Needed for switching outputs.",
          "use_ta": "Read values over the BL-NET's direct TCP connection. Needed for speed, power and energy.",
          "web_port": "Port of the web interface, usually 80",
          "ta_port": "Port of the direct connection, usually 40000",
          "can_node": "CAN node of the controller. Leave empty to keep the node selected on the BL-NET."
        }
      }
    },
    "error": {
      "cannot_connect": "Could not connect to the BL-NET",
      "invalid_config": "Invalid settings",
      "no_access_mode": "Enable the web interface, BLNET direct, or both",
      "no_data": "Connected, but the BL-NET returned no values. Check the password and the CAN node."
    },
    "abort": {
      "reconfigure_successful": "The BL-NET connection was changed"
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {"scan_interval": "Scan interval"},
        "data_description": {"scan_interval": "How often to fetch data from the BL-NET, in seconds"}
      }
    }
  },
```

`translations/de.json` gets the same structure with German text:

```json
  "config": {
    "step": {
      "user": {
        "title": "Mit dem BL-NET verbinden",
        "data": {
          "resource": "Adresse",
          "password": "Passwort",
          "use_web": "Weboberfläche verwenden",
          "use_ta": "BLNET direct verwenden",
          "web_port": "Port der Weboberfläche",
          "ta_port": "Port für BLNET direct",
          "can_node": "CAN-Knoten"
        },
        "data_description": {
          "resource": "Adresse des BL-NET, z. B. http://192.168.1.10",
          "password": "Passwort des Benutzers \"Experte\" der Weboberfläche. Leer lassen, wenn keins gesetzt ist.",
          "use_web": "Namen und Werte über die Weboberfläche lesen. Nötig zum Schalten von Ausgängen.",
          "use_ta": "Werte über die direkte TCP-Verbindung des BL-NET lesen. Nötig für Drehzahl, Leistung und Energie.",
          "web_port": "Port der Weboberfläche, meist 80",
          "ta_port": "Port der direkten Verbindung, meist 40000",
          "can_node": "CAN-Knoten des Reglers. Leer lassen, um den am BL-NET gewählten Knoten zu behalten."
        }
      },
      "reconfigure": {
        "title": "BL-NET-Verbindung ändern",
        "data": {
          "resource": "Adresse",
          "password": "Passwort",
          "use_web": "Weboberfläche verwenden",
          "use_ta": "BLNET direct verwenden",
          "web_port": "Port der Weboberfläche",
          "ta_port": "Port für BLNET direct",
          "can_node": "CAN-Knoten"
        },
        "data_description": {
          "resource": "Adresse des BL-NET, z. B. http://192.168.1.10",
          "password": "Passwort des Benutzers \"Experte\" der Weboberfläche. Leer lassen, wenn keins gesetzt ist.",
          "use_web": "Namen und Werte über die Weboberfläche lesen. Nötig zum Schalten von Ausgängen.",
          "use_ta": "Werte über die direkte TCP-Verbindung des BL-NET lesen. Nötig für Drehzahl, Leistung und Energie.",
          "web_port": "Port der Weboberfläche, meist 80",
          "ta_port": "Port der direkten Verbindung, meist 40000",
          "can_node": "CAN-Knoten des Reglers. Leer lassen, um den am BL-NET gewählten Knoten zu behalten."
        }
      }
    },
    "error": {
      "cannot_connect": "Keine Verbindung zum BL-NET",
      "invalid_config": "Ungültige Einstellungen",
      "no_access_mode": "Weboberfläche, BLNET direct oder beides aktivieren",
      "no_data": "Verbunden, aber das BL-NET hat keine Werte geliefert. Passwort und CAN-Knoten prüfen."
    },
    "abort": {
      "reconfigure_successful": "Die BL-NET-Verbindung wurde geändert"
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {"scan_interval": "Abfrageintervall"},
        "data_description": {"scan_interval": "Wie oft Daten vom BL-NET abgerufen werden, in Sekunden"}
      }
    }
  },
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_config_flow.py -q && uv run ruff check`
Expected: all pass. The autouse `mock_setup_entry` fixture keeps the reloads triggered by reconfigure and options from running the integration's setup.

- [ ] **Step 7: Commit**

```bash
git add custom_components/blnet/config_flow.py custom_components/blnet/manifest.json custom_components/blnet/translations tests/test_config_flow.py
git commit -m "Add config flow with YAML import, reconfigure and options"
```

---

### Task 4: Entry setup, YAML import, entity base and sensors

**Files:**
- Rewrite: `custom_components/blnet/__init__.py`
- Create: `custom_components/blnet/entity.py`
- Rewrite: `custom_components/blnet/sensor.py`
- Create: `custom_components/blnet/icons.json`
- Modify: `custom_components/blnet/translations/en.json`, `de.json` (add `entity.sensor`, `issues`)
- Delete: `tests/test_legacy_sensor.py` (its cases move into the new tests)
- Test: `tests/test_init.py`, `tests/test_sensor.py`

**Interfaces:**
- Consumes: `BLNETCoordinator`, `BLNETConfigEntry` (Task 2); config flow import step (Task 3).
- Produces:
  - `PLATFORMS` in `__init__.py` (sensor only in this task; Task 5 adds switch).
  - `class BLNETEntity(CoordinatorEntity[BLNETCoordinator])` with `__init__(coordinator, blnet_id: str)`, property `blnet_data -> dict[str, Any]` (the coordinator entry for this entity; only valid while `available`), `available` = coordinator success and key present, `_attr_has_entity_name = True`, device info, naming: `translation_key` = `data["domain"]` (or override), placeholders `{"id": str(id)}`, explicit `_attr_name` = web name when present.
  - Sensor unique ID `f"blnet_sensor_{blnet_id}"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_init.py`:

```python
"""Tests for setting up the BLNET integration."""
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er, issue_registry as ir
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
```

`tests/test_sensor.py`:

```python
"""Tests for BLNET sensors."""
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.blnet.const import CONF_USE_WEB


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("entity_id", "state", "device_class", "state_class", "unit"),
    [
        ("sensor.bl_net_ts6", "52.4", "temperature", "measurement", "°C"),
        ("sensor.bl_net_s16", "120", "volume_flow_rate", "measurement", "L/h"),
        ("sensor.bl_net_power_1", "6.984", "power", "measurement", "kW"),
        ("sensor.bl_net_energy_1", "362850.9", "energy", "total_increasing", "kWh"),
        ("sensor.bl_net_speed_1", "24", None, "measurement", None),
    ],
)
async def test_sensors(hass, mock_blnet, mock_config_entry, entity_id, state, device_class, state_class, unit):
    """Sensors get state, device class, state class and unit from the type."""
    await _setup(hass, mock_config_entry)
    s = hass.states.get(entity_id)
    assert s.state == state
    assert s.attributes.get("device_class") == device_class
    assert s.attributes.get("state_class") == state_class
    assert s.attributes.get("unit_of_measurement") == unit


async def test_unknown_analog_type(hass, mock_blnet, mock_config_entry):
    """An analog input without known type gets no class or unit."""
    mock_blnet.fetch.return_value["analog"][3] = {"value": 5, "type": None}
    await _setup(hass, mock_config_entry)
    s = hass.states.get("sensor.bl_net_analog_3")
    assert s.state == "5"
    assert "device_class" not in s.attributes
    assert "unit_of_measurement" not in s.attributes


async def test_digital_outputs_as_sensors_without_web(hass, mock_blnet, mock_config_entry):
    """Without the web interface, digital outputs are sensors."""
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_USE_WEB: False}
    )
    raw = mock_blnet.fetch.return_value
    for entry in raw["analog"].values():
        entry.pop("name")
    raw["digital"] = {1: {"value": 1}}
    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.bl_net_output_1").state == "True"
    assert hass.states.get("sensor.bl_net_analog_6").state == "52.4"


async def test_new_input_added_later(hass, mock_blnet, mock_config_entry, freezer: FrozenDateTimeFactory):
    """An input that appears in a later update gets an entity."""
    await _setup(hass, mock_config_entry)
    assert hass.states.get("sensor.bl_net_analog_7") is None
    mock_blnet.fetch.return_value["analog"][7] = {"value": 28.9, "type": "temperature"}
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_analog_7").state == "28.9"


async def test_missing_input_unavailable(hass, mock_blnet, mock_config_entry, freezer: FrozenDateTimeFactory):
    """An input that disappears (no sensor / broken wire) is unavailable, not stale."""
    await _setup(hass, mock_config_entry)
    del mock_blnet.fetch.return_value["analog"][6]
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bl_net_ts6").state == STATE_UNAVAILABLE
```

Note on entity IDs: with `has_entity_name` and device name "BL-NET", new entity IDs are `sensor.bl_net_<name>`; names come from the web interface ("TS6", "S16") or from the translation ("Power 1", "Speed 1", "Analog 3", "Output 1"). `mock_blnet.fetch.return_value` is a fresh deep copy per test, so mutating it is safe; the mock returns the same dict object on every call.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_init.py tests/test_sensor.py -q`
Expected: FAIL (no `async_setup_entry`; entities not created).

- [ ] **Step 3: Implement `custom_components/blnet/entity.py`**

```python
"""Base entity for the BLNET integration."""
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BLNETCoordinator


class BLNETEntity(CoordinatorEntity[BLNETCoordinator]):
    """An entity for one value of the BL-NET."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BLNETCoordinator,
        blnet_id: str,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the entity for coordinator.data[blnet_id]."""
        super().__init__(coordinator)
        self.blnet_id = blnet_id
        data = coordinator.data[blnet_id]
        self.output_id: int = data["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Technische Alternative",
            model="BL-NET",
            name="BL-NET",
        )
        # The translation key also selects the icon from icons.json
        self._attr_translation_key = translation_key or data["domain"]
        self._attr_translation_placeholders = {"id": str(data["id"])}
        if data["name"]:
            # Names configured on the controller, from the web interface
            self._attr_name = data["name"]

    @property
    def blnet_data(self) -> dict[str, Any]:
        """The current data of this entity; only valid while available."""
        return self.coordinator.data[self.blnet_id]

    @property
    def available(self) -> bool:
        """Unavailable if the update failed or this value is missing."""
        return super().available and self.blnet_id in self.coordinator.data
```

- [ ] **Step 4: Rewrite `custom_components/blnet/sensor.py`**

```python
"""Sensors for the BLNET integration."""
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_USE_WEB, SENSOR_DOMAINS
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity

# The coordinator polls, entities don't
PARALLEL_UPDATES = 0

# Sensor type (analog input type, or the domain otherwise) ->
# device class, state class, unit
SENSOR_TYPES = {
    "temperature": (SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT,
                    UnitOfTemperature.CELSIUS),
    "volume_flow": (SensorDeviceClass.VOLUME_FLOW_RATE, SensorStateClass.MEASUREMENT,
                    UnitOfVolumeFlowRate.LITERS_PER_HOUR),
    "radiation": (SensorDeviceClass.IRRADIANCE, SensorStateClass.MEASUREMENT,
                  UnitOfIrradiance.WATTS_PER_SQUARE_METER),
    "power": (SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT),
    "energy": (SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
               UnitOfEnergy.KILO_WATT_HOUR),
    # Speed level 0-30, not rpm
    "speed": (None, SensorStateClass.MEASUREMENT, None),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors, and more whenever new values appear."""
    coordinator = entry.runtime_data
    domains = SENSOR_DOMAINS if entry.data[CONF_USE_WEB] else (*SENSOR_DOMAINS, "digital")
    known: set[str] = set()

    @callback
    def add_new_sensors() -> None:
        new = [
            BLNETSensor(coordinator, blnet_id)
            for blnet_id, data in coordinator.data.items()
            if data["domain"] in domains and blnet_id not in known
        ]
        known.update(sensor.blnet_id for sensor in new)
        if new:
            async_add_entities(new)

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


class BLNETSensor(BLNETEntity, SensorEntity):
    """A value of the BL-NET."""

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the sensor."""
        domain = coordinator.data[blnet_id]["domain"]
        # Digital outputs shown as sensors are named "Output <id>"
        super().__init__(coordinator, blnet_id, "output" if domain == "digital" else None)
        # Unchanged from the YAML setup, so existing entities are kept
        self._attr_unique_id = f"blnet_sensor_{blnet_id}"
        device_class, state_class, unit = SENSOR_TYPES.get(
            coordinator.data[blnet_id]["type"], (None, None, None)
        )
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.blnet_data["value"]
```

Note: device class/unit are fixed at creation. An input's type only changes if the controller is reprogrammed; a reload picks that up.

- [ ] **Step 5: Rewrite `custom_components/blnet/__init__.py`**

```python
"""The BLNET integration: UVR1611 via BL-NET."""
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_RESOURCE,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_NODE,
    CONF_TA_PORT,
    CONF_USE_TA,
    CONF_USE_WEB,
    CONF_WEB_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TA_PORT,
    DEFAULT_WEB_PORT,
    DOMAIN,
)
from .coordinator import BLNETConfigEntry, BLNETCoordinator

PLATFORMS = [Platform.SENSOR]

# Old YAML configuration, only imported into a config entry
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_RESOURCE): cv.url,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_NODE): cv.positive_int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
                vol.Optional(CONF_WEB_PORT, default=DEFAULT_WEB_PORT): cv.positive_int,
                vol.Optional(CONF_TA_PORT, default=DEFAULT_TA_PORT): cv.positive_int,
                vol.Optional(CONF_USE_WEB, default=True): cv.boolean,
                vol.Optional(CONF_USE_TA, default=False): cv.boolean,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import a YAML configuration into a config entry."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=dict(config[DOMAIN])
            )
        )
        ir.async_create_issue(
            hass,
            DOMAIN,
            "deprecated_yaml",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Set up the BL-NET from a config entry."""
    coordinator = BLNETCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BLNETConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

The old `switch.py` still has `setup_platform` and is not forwarded until Task 5; leave it untouched in this task.

- [ ] **Step 6: Icons and translations**

`custom_components/blnet/icons.json`:

```json
{
  "entity": {
    "sensor": {
      "speed": {"default": "mdi:speedometer"},
      "output": {"default": "mdi:flash"}
    }
  }
}
```

Add to `translations/en.json`:

```json
  "entity": {
    "sensor": {
      "analog": {"name": "Analog {id}"},
      "speed": {"name": "Speed {id}"},
      "power": {"name": "Power {id}"},
      "energy": {"name": "Energy {id}"},
      "output": {"name": "Output {id}"}
    }
  },
  "issues": {
    "deprecated_yaml": {
      "title": "BLNET YAML configuration is deprecated",
      "description": "Your `blnet:` configuration was imported into the UI. Remove the `blnet:` block from configuration.yaml and restart Home Assistant. Change settings under Settings > Devices & services > BLNET from now on."
    }
  },
```

Add to `translations/de.json`:

```json
  "entity": {
    "sensor": {
      "analog": {"name": "Analog {id}"},
      "speed": {"name": "Drehzahl {id}"},
      "power": {"name": "Leistung {id}"},
      "energy": {"name": "Energie {id}"},
      "output": {"name": "Ausgang {id}"}
    }
  },
  "issues": {
    "deprecated_yaml": {
      "title": "BLNET-YAML-Konfiguration ist veraltet",
      "description": "Deine `blnet:`-Konfiguration wurde in die Oberfläche übernommen. Entferne den `blnet:`-Block aus configuration.yaml und starte Home Assistant neu. Einstellungen änderst du ab jetzt unter Einstellungen > Geräte & Dienste > BLNET."
    }
  },
```

- [ ] **Step 7: Delete the legacy sensor tests**

```bash
git rm -q tests/test_legacy_sensor.py
```

(Its cases are covered by `test_coordinator.py` — digital bools, failed fetch, connect retry — and `test_sensor.py` — types, units, unknown type.)

- [ ] **Step 8: Run tests**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass except `tests/test_legacy_switch.py` may still pass (it tests the old switch classes, untouched). If an entity ID in the tests differs because of slugification, print `hass.states.async_entity_ids("sensor")` once and fix the test IDs, not the code.

- [ ] **Step 9: Commit**

```bash
git add -A custom_components/blnet tests
git commit -m "Set up from config entry with coordinator and import YAML"
```

---

### Task 5: Switch platform on the coordinator

**Files:**
- Rewrite: `custom_components/blnet/switch.py`
- Modify: `custom_components/blnet/__init__.py` (`PLATFORMS`)
- Modify: `custom_components/blnet/icons.json`, `translations/en.json`, `translations/de.json` (`entity.switch`)
- Delete: `tests/test_legacy_switch.py`
- Test: `tests/test_switch.py`

**Interfaces:**
- Consumes: `BLNETEntity` (Task 4), `BLNETCoordinator.async_set_output(output_id, state)` (Task 2).
- Produces: `BLNETOutputSwitch` (unique ID `blnet_switch_<id>`, translation key `output`), `BLNETModeSwitch` (unique ID `blnet_mode_switch_<id>`, translation key `output_mode` or `output_mode_named`, `EntityCategory.CONFIG`).

- [ ] **Step 1: Write the failing tests**

`tests/test_switch.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_switch.py -q`
Expected: FAIL (no switch entities).

- [ ] **Step 3: Rewrite `custom_components/blnet/switch.py`**

```python
"""Switches for the digital outputs of the UVR1611."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_USE_WEB
from .coordinator import BLNETConfigEntry, BLNETCoordinator
from .entity import BLNETEntity

# One command at a time to the web interface
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BLNETConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add two switches per digital output, if the web interface is used."""
    if not entry.data[CONF_USE_WEB]:
        return
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_switches() -> None:
        new: list[SwitchEntity] = []
        for blnet_id, data in coordinator.data.items():
            if data["domain"] == "digital" and blnet_id not in known:
                known.add(blnet_id)
                new += [
                    BLNETOutputSwitch(coordinator, blnet_id),
                    BLNETModeSwitch(coordinator, blnet_id),
                ]
        if new:
            async_add_entities(new)

    add_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(add_new_switches))


class BLNETOutputSwitch(BLNETEntity, SwitchEntity):
    """Switch a digital output on or off. Sets the output to HAND."""

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, blnet_id, "output")
        self._attr_unique_id = f"blnet_switch_{self.output_id}"

    @property
    def is_on(self) -> bool:
        """Return whether the output is on."""
        return self.blnet_data["value"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return AUTO or HAND."""
        return {"mode": self.blnet_data["mode"]}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the output on (HAND/EIN)."""
        await self.coordinator.async_set_output(self.output_id, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the output off (HAND/AUS)."""
        await self.coordinator.async_set_output(self.output_id, "off")


class BLNETModeSwitch(BLNETEntity, SwitchEntity):
    """On means the controller switches the output (AUTO)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BLNETCoordinator, blnet_id: str) -> None:
        """Initialize the switch."""
        named = bool(coordinator.data[blnet_id]["name"])
        super().__init__(
            coordinator, blnet_id, "output_mode_named" if named else "output_mode"
        )
        self._attr_unique_id = f"blnet_mode_switch_{self.output_id}"
        if named:
            # The name comes from the translation with the output's name in it
            del self._attr_name
            self._attr_translation_placeholders = {
                "name": coordinator.data[blnet_id]["name"]
            }

    @property
    def is_on(self) -> bool:
        """Return whether the output is in AUTO mode."""
        return self.blnet_data["mode"] != "HAND"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Hand control back to the controller (AUTO)."""
        await self.coordinator.async_set_output(self.output_id, "auto")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch to HAND, keeping the output's current value."""
        state = "on" if self.blnet_data["value"] else "off"
        await self.coordinator.async_set_output(self.output_id, state)
```

No separate optimistic state is kept: `async_set_output` requests a refresh right after the command, and the fetched data is what the switch shows (`test_refresh_after_command`).

- [ ] **Step 4: Forward the switch platform**

`__init__.py`: `PLATFORMS = [Platform.SENSOR, Platform.SWITCH]`.

- [ ] **Step 5: Icons and translations**

`icons.json` `entity` gets:

```json
    "switch": {
      "output": {"default": "mdi:flash", "state": {"off": "mdi:flash-off"}},
      "output_mode": {"default": "mdi:cog", "state": {"off": "mdi:cog-off"}},
      "output_mode_named": {"default": "mdi:cog", "state": {"off": "mdi:cog-off"}}
    }
```

`translations/en.json` `entity` gets:

```json
    "switch": {
      "output": {"name": "Output {id}"},
      "output_mode": {"name": "Output {id} automatic"},
      "output_mode_named": {"name": "{name} automatic"}
    }
```

`translations/de.json` `entity` gets:

```json
    "switch": {
      "output": {"name": "Ausgang {id}"},
      "output_mode": {"name": "Ausgang {id} Automatik"},
      "output_mode_named": {"name": "{name} Automatik"}
    }
```

- [ ] **Step 6: Delete legacy switch tests, run everything**

```bash
git rm -q tests/test_legacy_switch.py
uv run pytest -q && uv run ruff check
```

Expected: all pass. The test entity IDs `switch.bl_net_pumpe_hk1_automatic` assume the English translation; tests run with English.

- [ ] **Step 7: Commit**

```bash
git add -A custom_components/blnet tests
git commit -m "Move switches to the coordinator"
```

---

### Task 6: Diagnostics and translation consistency

**Files:**
- Create: `custom_components/blnet/diagnostics.py`
- Test: `tests/test_diagnostics.py`, `tests/test_translations.py`

**Interfaces:**
- Consumes: `BLNETConfigEntry`, `coordinator.data`.
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_diagnostics.py`:

```python
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
```

`tests/test_translations.py`:

```python
"""English and German translations have the same keys."""
import json
from pathlib import Path

TRANSLATIONS = Path(__file__).parent.parent / "custom_components/blnet/translations"


def _keys(tree, prefix=""):
    if not isinstance(tree, dict):
        return {prefix}
    return set().union(*(_keys(v, f"{prefix}.{k}") for k, v in tree.items()))


def test_same_keys():
    en = json.loads((TRANSLATIONS / "en.json").read_text())
    de = json.loads((TRANSLATIONS / "de.json").read_text())
    assert _keys(en) == _keys(de)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_diagnostics.py tests/test_translations.py -q`
Expected: diagnostics FAIL (module missing); translations PASS if Tasks 2-5 kept both files in sync (fix any difference it reports).

- [ ] **Step 3: Implement `custom_components/blnet/diagnostics.py`**

```python
"""Diagnostics for the BLNET integration."""
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import BLNETConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BLNETConfigEntry
) -> dict[str, Any]:
    """Return the configuration and the last data, without the password."""
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), {CONF_PASSWORD}),
            "options": dict(entry.options),
        },
        "data": entry.runtime_data.data,
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q && uv run ruff check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/blnet/diagnostics.py tests/test_diagnostics.py tests/test_translations.py
git commit -m "Add diagnostics"
```

---

### Task 7: Coverage gate, quality scale status, documentation

**Files:**
- Create: `custom_components/blnet/quality_scale.yaml`
- Modify: `.github/workflows/tests.yml`, `README.md`, `CLAUDE.md`, `hacs.json` (only if needed)
- Delete: `configuration.yaml` example references to `scan_interval` etc. in README (replaced by UI docs)

- [ ] **Step 1: Coverage gate**

Run: `uv run pytest --cov=custom_components.blnet --cov-report=term-missing --cov-fail-under=95`
Expected: PASS with every module ≥ 95 %. If a module is below, add a test for the uncovered lines shown in `Missing` (do not exclude lines). Then use the same command in CI (`.github/workflows/tests.yml` test step).

- [ ] **Step 2: Write `custom_components/blnet/quality_scale.yaml`**

```yaml
rules:
  # Bronze
  action-setup:
    status: exempt
    comment: The integration has no service actions.
  appropriate-polling: done
  brands:
    status: exempt
    comment: Custom integration; brand assets would be a separate PR to home-assistant/brands.
  common-modules: done
  config-flow-test-coverage: done
  config-flow: done
  dependency-transparency: done
  docs-actions:
    status: exempt
    comment: The integration has no service actions.
  docs-triggers:
    status: exempt
    comment: The integration has no triggers.
  docs-conditions:
    status: exempt
    comment: The integration has no conditions.
  docs-high-level-description: done
  docs-installation-instructions: done
  docs-removal-instructions: done
  entity-event-setup: done
  entity-unique-id: done
  has-entity-name: done
  runtime-data: done
  test-before-configure: done
  test-before-setup: done
  unique-config-entry: done

  # Silver
  action-exceptions: done
  config-entry-unloading: done
  docs-configuration-parameters: done
  docs-installation-parameters: done
  entity-unavailable: done
  integration-owner: done
  log-when-unavailable: done
  parallel-updates: done
  reauthentication-flow:
    status: exempt
    comment: >-
      pyblnet's web interface returns empty data instead of raising on a failed
      login, so a wrong password can't be told apart from a network error. The
      reconfigure flow is used to change the password.
  test-coverage: done

  # Gold
  devices: done
  diagnostics: done
  discovery-update-info:
    status: exempt
    comment: The BL-NET can't be discovered.
  discovery:
    status: exempt
    comment: The BL-NET has no known mDNS, SSDP or DHCP signature.
  docs-data-update: done
  docs-examples: done
  docs-known-limitations: done
  docs-supported-devices: done
  docs-supported-functions: done
  docs-troubleshooting: done
  docs-use-cases: done
  dynamic-devices: done
  entity-category: done
  entity-device-class: done
  entity-disabled-by-default:
    status: exempt
    comment: Every input and output on the controller is wired on purpose; none are noisy.
  entity-translations: done
  exception-translations: done
  icon-translations: done
  reconfiguration-flow: done
  repair-issues: done
  stale-devices:
    status: exempt
    comment: Exactly one device per config entry.

  # Platinum
  async-dependency:
    status: exempt
    comment: pyblnet is synchronous.
  inject-websession:
    status: exempt
    comment: pyblnet uses requests and raw sockets.
  strict-typing: todo
```

- [ ] **Step 3: Rewrite README.md**

Sections, in this order, with real content (no placeholders):
1. Title, HACS badge, one-paragraph description (UVR1611 heating controller by Technische Alternative, read and switch via the BL-NET gateway, web interface and/or BLNET direct).
2. **Supported devices**: UVR1611 behind a BL-NET (DL and CAN bus modes). Other TA controllers untested.
3. **Installation**: HACS custom repository `https://github.com/dereisele/ha_blnet` (type Integration), install, restart; or copy `custom_components/blnet`.
4. **Setup**: Settings > Devices & services > Add integration > BLNET; table of the setup fields with the `data_description` texts from `translations/en.json`; the options (scan interval, default 360 s, min 10 s); reconfigure via the entry's menu.
5. **Migrating from YAML**: the `blnet:` block is imported on the next start, entities and their custom names are kept, then remove the block (repair notice).
6. **Entities**: table: analog inputs (device class by input type: temperature °C, volume flow L/h, irradiance W/m²), speed (level 0-30, no unit), power kW, energy kWh (Energy dashboard), digital outputs (two switches each with web interface: output and "… automatic"; sensors without it). Turning an output switch sets the output to HAND until the automatic switch is turned on again.
7. **How data is updated**: polling every scan interval; a fetch takes up to a few seconds; values missing from a fetch (no sensor / broken wire) make the entity unavailable.
8. **Automation example**: YAML automation that notifies when `sensor.bl_net_ts8` (boiler top) drops below 45 °C, using `numeric_state`.
9. **Use cases**: monitoring buffer/boiler temperatures, solar yield via the heat meter in the Energy dashboard, switching pumps manually.
10. **Known limitations**: one BL-NET per Home Assistant; switching needs the web interface; speed/power/energy need BLNET direct; no reauth flow (use reconfigure); deleting the integration entry removes its entities including custom names.
11. **Troubleshooting**: entities unavailable (check network, try the BL-NET web page, wrong password shows "no values" in setup); debug logging snippet for `custom_components.blnet` and `pyblnet`; download diagnostics.
12. **Removal**: Settings > Devices & services > BLNET > Delete; remove via HACS; note about custom names.
13. **Development**: `uv sync`, `uv run ruff check`, `uv run pytest --cov=custom_components.blnet`.
14. **Contributions**: link to pyblnet fork.

- [ ] **Step 4: Update CLAUDE.md**

Replace the Commands and Architecture sections to describe: pytest instead of unittest (`uv run pytest`, single test `uv run pytest tests/test_switch.py::test_mode_switch`), Python 3.14, the file layout table from this plan, coordinator data shape (`"blnet <domain> <id>" -> {id, domain, name, value, type, mode}`, rebuilt every update), unique ID formats (must never change), config entry data vs options, `quality_scale.yaml`. Remove the YAML/`load_platform` description and the "repo root doubles as HA config" paragraph stays (it's still true for manual testing).

- [ ] **Step 5: Run everything**

Run: `uv run ruff check && uv run pytest --cov=custom_components.blnet --cov-fail-under=95 -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A custom_components/blnet/quality_scale.yaml .github README.md CLAUDE.md
git commit -m "Document the UI setup and track the quality scale"
```

---

### Task 8: Manual verification against the real BL-NET and the local HA config

**Files:** none committed (local HA runtime files are git-ignored).

- [ ] **Step 1: Back up the local HA storage**

```bash
cp -a .storage /tmp/claude-1000/-home-alexander-develop-privat-ha-blnet/7550942d-8ac6-435a-b670-f06f1c5d024b/scratchpad/storage-backup
```

- [ ] **Step 2: Start HA with the existing YAML block**

`configuration.yaml` still contains `blnet:` (direct only, 192.168.100.19). Run in the background: `uv run hass -c . ` and wait until `home-assistant.log` shows the integration loaded (or 2 minutes).

- [ ] **Step 3: Check the result**

```bash
python - <<'EOF'
import json
entries = json.load(open('.storage/core.config_entries'))['data']['entries']
print([ (e['domain'], e['title'], e['options']) for e in entries if e['domain'] == 'blnet'])
reg = json.load(open('.storage/core.entity_registry'))['data']['entities']
bl = [e for e in reg if e['platform'] == 'blnet']
print(len(bl), 'entities;', sum(1 for e in bl if e['config_entry_id']), 'linked to the entry')
issues = json.load(open('.storage/repairs.issue_registry'))['data']['issues']
print([i['issue_id'] for i in issues if i['domain'] == 'blnet'])
EOF
grep -iE "blnet|pyblnet" home-assistant.log | grep -iE "error|warn" | tail
```

Expected: one `blnet` entry, the 38 existing entities linked to it with unchanged `entity_id`s, issue `deprecated_yaml`, no errors. Analog 1-5 and 15 entities are unavailable (no data since pyblnet 0.13.0).

- [ ] **Step 4: Stop HA, report the results to Alexander**
