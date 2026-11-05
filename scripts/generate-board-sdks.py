#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate in-project Workshop device SDKs for Zephyr boards.

Usage: generate-board-sdks.py <zephyr>/boards <output-dir>

For every board found in the Zephyr tree, infer the USB debug probe and
serial console the board exposes to the host, and write an in-project
Workshop SDK under <output-dir>/<vendor>/<board>/ in the same shape as
https://ubuntu.com/zephyr/docs/latest/tutorials/workshop-flash-hardware/
"""

import re
import sys
from pathlib import Path

import yaml

# Boards without physical USB hardware.
SKIP_VENDORS = {"qemu", "native", "renode", "xen", "acrn", "shields", "common"}

# Probe kinds: (usb vendor id, plug suffixes) -> description.
PROBES = {
    "stlink":  ("0483", "ST-LINK"),
    "jlink":   ("1366", "SEGGER J-Link"),
    "nxp":     ("1fc9", "NXP MCU-Link / LPC-Link2"),
    "xds110":  ("0451", "TI XDS110"),
    "kitprog": ("04b4", "Infineon KitProg"),
    "edbg":    ("03eb", "Microchip EDBG / nEDBG"),
    "pkob":    ("04d8", "Microchip PKOB4"),
    "nulink":  ("0416", "Nuvoton Nu-Link"),
    "daplink": ("0d28", "Arm DAPLink / CMSIS-DAP"),
    "gdlink":  ("28e9", "GigaDevice GD-Link"),
    "wchlink": ("1a86", "WCH-Link"),
    "bmp":     ("1d50", "Black Magic Probe"),
    "ftdi":    ("0403", "FTDI JTAG/UART bridge"),
    "esp":     ("303a", "Espressif USB-Serial/JTAG"),
    "rpi":     ("2e8a", "Raspberry Pi Debug Probe"),
}

# Vendor USB IDs for boards that enumerate natively (UF2, bossac, DFU, CDC ACM).
NATIVE_USB_VENDORS = {
    "raspberrypi": "2e8a", "adafruit": "239a", "arduino": "2341",
    "seeed": "2886", "sparkfun": "1b4f", "pjrc": "16c0", "particle": "2b04",
    "pimoroni": "2e8a", "waveshare": "2e8a", "makerdiary": "2886",
    "nordic": "1915", "wch": "1a86", "weact": "0483", "vcc-gnd": "0483",
    "96boards": "0483", "electronut": "1915", "fobe": "1915",
    "solderedelectronics": "2e8a", "01space": "2e8a", "arm": "0d28",
}

# Common USB-UART bridges found on Espressif and other dev boards.
UART_BRIDGES = {"cp210x": "10c4", "ch34x": "1a86", "ftdi": "0403"}

DOC_PATTERNS = [
    ("stlink", r"st-?link"),
    ("jlink", r"j-?link\s*(ob|on-?board)|on-?board\s+(segger\s+)?j-?link|interface mcu.*j-?link"),
    ("nxp", r"mcu-?link|lpc-?link|opensda"),
    ("xds110", r"xds110"),
    ("kitprog", r"kitprog"),
    ("pkob", r"pkob"),
    ("edbg", r"\bn?edbg\b"),
    ("nulink", r"nu-?link"),
    ("gdlink", r"gd-?link"),
    ("wchlink", r"wch-?link"),
    ("daplink", r"daplink|cmsis-dap"),
    ("ftdi", r"ft2232|ft4232|ftdi"),
]

RUNNER_PROBES = {
    "stm32cubeprogrammer": "stlink", "openocd-stm32": "stlink",
    "stlink_gdbserver": "stlink", "nrfjprog": "jlink", "nrfutil": "jlink",
    "openocd-nrf5": "jlink", "jlink": "jlink", "linkserver": "nxp",
    "spsdk": "nxp", "esp32": "esp", "blackmagicprobe": "bmp",
    "wchisp": "wchlink", "minichlink": "wchlink",
    "openocd-adi-max32": "daplink", "pyocd": "daplink",
}

NATIVE_RUNNERS = {"uf2", "bossac", "dfu-util", "teensy"}

PIP_TOOLS = {"esp32": "esptool", "pyocd": "pyocd"}


def runners(board_dir):
    cmake = board_dir / "board.cmake"
    if not cmake.exists():
        return []
    text = cmake.read_text(errors="ignore")
    return re.findall(r"boards/common/([\w.-]+?)\.boards?\.cmake", text)


def doc_text(board_dir):
    parts = []
    for p in board_dir.glob("doc/*.rst"):
        parts.append(p.read_text(errors="ignore"))
    return "\n".join(parts).lower()


def detect_probe(vendor, run, doc):
    for kind, pat in DOC_PATTERNS:
        if re.search(pat, doc):
            return kind
    for r in run:
        if r in RUNNER_PROBES:
            return RUNNER_PROBES[r]
        if r in NATIVE_RUNNERS:
            return None
    return None


def plug_name(board):
    return re.sub(r"[^a-z0-9-]", "-", board.lower()).strip("-")


def build_sdk(vendor, board, socs, run, doc):
    name = plug_name(board)
    plugs = {}
    comments = {}
    probe = detect_probe(vendor, run, doc)
    rp2 = any(s.startswith("rp2") for s in socs)
    if rp2:
        # Raspberry Pi Debug Probe and RP2xxx BOOTSEL/CDC ACM share VID 2e8a.
        probe = "rpi"
    elif vendor == "bflb" or any(s.startswith("bl") for s in socs if vendor in {"aithinker", "doiting", "bflb"}):
        probe = "uart"

    if probe == "esp":
        plugs[f"{name}-usb-jtag"] = ("usb", PROBES["esp"][0])
        comments[f"{name}-usb-jtag"] = "built-in USB-Serial/JTAG (where present)"
        plugs[f"{name}-usb-console"] = ("tty", PROBES["esp"][0])
        comments[f"{name}-usb-console"] = "built-in USB-Serial/JTAG console"
        for bridge, vid in UART_BRIDGES.items():
            plugs[f"{name}-{bridge}-serial"] = ("tty", vid)
            comments[f"{name}-{bridge}-serial"] = f"{bridge.upper()} USB-UART bridge"
    elif probe == "uart":
        for bridge, vid in UART_BRIDGES.items():
            plugs[f"{name}-{bridge}-serial"] = ("tty", vid)
            comments[f"{name}-{bridge}-serial"] = f"{bridge.upper()} USB-UART bridge"
    elif probe:
        vid, desc = PROBES[probe]
        plugs[f"{name}-probe"] = ("usb", vid)
        comments[f"{name}-probe"] = f"debug probe: {desc}"
        plugs[f"{name}-console"] = ("tty", vid)
        comments[f"{name}-console"] = f"console: {desc} virtual COM port"

    native = NATIVE_USB_VENDORS.get(vendor)
    if rp2:
        native = "2e8a"
    if native and (rp2 or vendor == "arduino" or not plugs
                   or any(r in NATIVE_RUNNERS for r in run)):
        if not any(v == native and s == "tty" for s, v in plugs.values()) or not plugs:
            plugs[f"{name}-usb"] = ("usb", native)
            comments[f"{name}-usb"] = "native USB bootloader (UF2/DFU/bossac)"
            plugs[f"{name}-serial"] = ("tty", native)
            comments[f"{name}-serial"] = "native USB CDC ACM console"

    if not plugs:
        return None, None

    lines = [f"name: {name}", "plugs:"]
    for plug, (subsystem, vid) in plugs.items():
        lines.append(f"  {plug}:  # {comments[plug]}")
        lines.append("    interface: custom-device")
        lines.append(f"    subsystem: {subsystem}")
        lines.append(f'    vendorid: "{vid}"')
    sdk = "\n".join(lines) + "\n"

    tools = sorted({PIP_TOOLS[r] for r in run if r in PIP_TOOLS})
    hook = None
    if tools:
        hook = ("#!/bin/bash\nset -e\n"
                "source /var/lib/workshop/sdk/zephyr/venv/bin/activate\n"
                f"pip install {' '.join(tools)}\n")
    return sdk, hook


def boards_in(board_yml):
    data = yaml.safe_load(board_yml.read_text())
    if "board" in data:
        return [data["board"]]
    return data.get("boards", [])


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    skipped = []
    count = 0
    for board_yml in sorted(src.glob("*/**/board.yml")):
        board_dir = board_yml.parent
        vendor_dir = board_yml.relative_to(src).parts[0]
        if vendor_dir in SKIP_VENDORS:
            continue
        run = runners(board_dir)
        doc = doc_text(board_dir)
        for b in boards_in(board_yml):
            vendor = b.get("vendor", vendor_dir)
            socs = [s["name"] for s in b.get("socs", [])]
            sdk, hook = build_sdk(vendor, b["name"], socs, run, doc)
            if sdk is None:
                skipped.append(f"{vendor}/{b['name']}")
                continue
            dest = out / vendor / plug_name(b["name"])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "sdk.yaml").write_text(sdk)
            if hook:
                h = dest / "hooks" / "setup-project"
                h.parent.mkdir(exist_ok=True)
                h.write_text(hook)
                h.chmod(0o755)
            count += 1
    (out / "SKIPPED.txt").write_text(
        "# Boards with no detectable USB probe or console\n"
        + "\n".join(skipped) + "\n")
    print(f"generated {count}, skipped {len(skipped)}")


if __name__ == "__main__":
    main()
