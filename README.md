[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

# BLNET custom component for Home Assistant

Reads and switches the freely programmable heating controller [UVR1611 by Technische Alternative](https://www.ta.co.at/en/freely-programmable/uvr1611/) in Home Assistant, via the BL-NET gateway. It can talk to the BL-NET through its web interface, through the BLNET direct protocol, or both. Everything is set up in the UI.

![Configured groups containing all available BLNet-supplied sensors](https://github.com/user-attachments/assets/e7028fdb-66aa-466f-9be0-22894f422e57)

## Supported devices

The UVR1611 behind a BL-NET (DL and CAN bus modes). Other Technische Alternative controllers are untested.

## Installation

Add `https://github.com/dereisele/ha_blnet` as a custom repository (type *Integration*) to [HACS](https://hacs.xyz/), install **BLNET** and restart Home Assistant. Alternatively copy `custom_components/blnet` into the `custom_components` directory of your Home Assistant configuration and restart.

The integration depends on [pyblnet](https://github.com/dereisele/pyblnet) from GitHub, which Home Assistant installs automatically.

## Setup

Go to **Settings > Devices & services > Add integration** and pick **BLNET**.

| Field | Default | Description |
| --- | --- | --- |
| Address | | Address of the BL-NET, e.g. `http://192.168.1.10` |
| Password | empty | Password of the "Expert" user of the web interface. Leave empty if none is set. |
| Use web interface | on | Read names and values from the web interface. Needed for switching outputs. |
| Use BLNET direct | off | Read values over the BL-NET's direct TCP connection. Needed for speed, power and energy. |
| Web interface port | 80 | Port of the web interface |
| BLNET direct port | 40000 | Port of the direct connection |
| CAN node | empty | CAN node of the controller. Leave empty to keep the node selected on the BL-NET. |

At least one of the web interface and BLNET direct must be on. The connection is tested before the entry is created.

**Options** (the entry's *Configure* button): the scan interval in seconds, default 360, minimum 10.

To change the address, ports, password, access modes or CAN node later, use **Reconfigure** in the entry's menu.

## Migrating from YAML

If your `configuration.yaml` still has a `blnet:` block, it is imported into a config entry on the next start (the scan interval becomes an option). Remove the block afterwards; a repair notice reminds you.

Your existing entities are kept. Entity IDs of existing entities never change, and names you set in the UI are kept as they are. Entities that were never renamed now show the device name in front (e.g. "BL-NET TS6"), because entity names are now relative to the device.

## Entities

| Entity | Details |
| --- | --- |
| Analog inputs | Sensors. Device class by input type: temperature (°C), volume flow (L/h), irradiance (W/m²) |
| Speed | Sensor, level 0-30, no unit (BLNET direct only) |
| Power | Sensor in kW (BLNET direct only) |
| Energy | Sensor in kWh, usable in the Energy dashboard (BLNET direct only) |
| Digital outputs | With the web interface, two switches each: the output and "... automatic". Without it, sensors. |

Turning an output switch on or off sets the output to `HAND` until the "automatic" switch is turned on again (on = `AUTO`, off = `HAND`).

New installs get entity IDs like `sensor.bl_net_<name>`.

## How data is updated

The BL-NET is polled every scan interval; a fetch takes up to a few seconds. Values missing from a fetch make the entity unavailable. pyblnet leaves out inputs without a sensor (raw 409.5 °C), so those entities show unavailable; you can delete them.

## Automation example

Notify when the boiler top drops below 45 °C. Replace `sensor.bl_net_ts8` with your own entity ID.

```yaml
automation:
  - alias: Boiler is cold
    triggers:
      - trigger: numeric_state
        entity_id: sensor.bl_net_ts8
        below: 45
    actions:
      - action: notify.notify
        data:
          message: Boiler top is below 45 °C
```

## Use cases

- Monitor buffer and boiler temperatures.
- Track solar yield through the heat meter in the Energy dashboard.
- Switch pumps manually.

## Known limitations

- One BL-NET per Home Assistant.
- Switching outputs needs the web interface; speed, power and energy need BLNET direct.
- No reauthentication flow: a wrong password can't be told apart from a network error. Use reconfigure to change the password.
- Deleting the integration entry removes its entities, including custom names.

## Troubleshooting

- Entities unavailable: check the network and open the BL-NET web page in a browser.
- All entities unavailable with "returned no values" in the log: the web password was changed or is wrong, or another web session is open on the BL-NET. Fix the password via Settings > Devices & services > BLNET > Reconfigure, and close other web sessions.
- Setup says "no values": check the password and the CAN node.
- Debug logging:

  ```yaml
  logger:
    logs:
      custom_components.blnet: debug
      pyblnet: debug
  ```

- Download diagnostics from the device page when reporting a problem (the password is redacted).

## Removal

Settings > Devices & services > BLNET > three dots > Delete. This removes the entities, including their custom names. To remove the code, uninstall BLNET in HACS (or delete `custom_components/blnet`) and restart.

## Development

```bash
uv sync
uv run ruff check
uv run pytest --cov=custom_components.blnet
```

## Contributions

Feel free to open Pull Requests here or at
the backend python library [pyblnet](https://github.com/dereisele/pyblnet).
