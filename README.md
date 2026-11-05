# Zephyr-workshops
A library of workshop files for Zephyr development.

## Board device SDKs

`boards/<vendor>/<board>/` contains a ready-made in-project Workshop device SDK
for each Zephyr 4.4 board that exposes a USB debug probe or serial console,
following
[Create a device SDK](https://ubuntu.com/zephyr/docs/latest/tutorials/workshop-flash-hardware/#create-a-device-sdk).

Each SDK declares `custom-device` plugs that match the board's USB vendor ID:

- `<board>-probe` / `<board>-console`: on-board debug probe (`usb`) and its
  virtual COM port (`tty`), such as ST-LINK, J-Link, MCU-Link or XDS110.
- `<board>-usb` / `<board>-serial`: native USB bootloader and CDC ACM console
  for boards flashed via UF2, DFU or bossac.
- `<board>-<bridge>-serial`: common USB-UART bridges (CP210x, CH34x, FTDI),
  used by Espressif and Bouffalo Lab boards.

Some SDKs also ship a `hooks/setup-project` that reinstalls the Python runner
tools (`esptool`, `pyocd`) into the Zephyr virtual environment.

Plugs match on vendor ID only, so they work across probe firmware revisions.
Remove plugs your hardware does not have, and add a `productid` to narrow a
match if several devices from the same vendor are attached.

### Usage

Copy the board directory into your project and list it after the `zephyr` SDK
in `.workshop/zephyr-26-04.yaml`:

```console
$ cp -r zephyr-workshops/boards/st/nucleo-f401re .workshop/
```

```yaml
sdks:
  # Existing SDK entries...
  - name: project-nucleo-f401re
```

Then apply the definition and connect the plugs:

```console
$ workshop refresh zephyr-26-04
$ workshop connect zephyr-26-04/nucleo-f401re:nucleo-f401re-probe :custom-device
$ workshop connect zephyr-26-04/nucleo-f401re:nucleo-f401re-console :custom-device
```

### Regenerating

The SDKs are generated from a Zephyr tree:

```console
$ scripts/generate-board-sdks.py <zephyr>/boards boards
```

Boards with no detectable USB interface (emulators, simulators, FPGA and
SoC-only boards, and so on) are listed in `boards/SKIPPED.txt`.
