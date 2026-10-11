#!/usr/bin/env python3
"""Print the /dev/cu.* port of the test P4X-EYE, found by USB descriptor only.

Never opens a serial port (no reset, no download mode). The ESP32-P4's
USB-Serial/JTAG reports the chip MAC as its USB serial number, so matching it
against UNIT_MAC (tools/stt_p4/private/unit.env) identifies the unit.
Exit 0 + port on stdout when found; exit 1 otherwise. Never prints the MAC.
"""
import os, plistlib, re, subprocess, sys
from pathlib import Path

# UNIT_MAC from the environment, else from tools/stt_p4/private/unit.env (git-ignored; HW1_STT_P4 overrides the folder)
ENV = Path(os.environ.get('HW1_STT_P4', Path(__file__).resolve().parents[1] / 'stt_p4')) / 'private' / 'unit.env'
mac = os.environ.get('UNIT_MAC')
if not mac and ENV.exists():
    m = re.search(r'^UNIT_MAC=(\S+)', ENV.read_text(), re.M)
    mac = m and m.group(1)
if not mac:
    sys.exit('UNIT_MAC not set')
mac = mac.lower()

tree = plistlib.loads(subprocess.check_output(['ioreg', '-a', '-r', '-c', 'IOUSBHostDevice', '-l']))


def callouts(node):
    if isinstance(node, dict):
        if 'IOCalloutDevice' in node:
            yield node['IOCalloutDevice']
        for child in node.get('IORegistryEntryChildren', []):
            yield from callouts(child)


found = []
for dev in tree:
    if dev.get('idVendor') == 0x303A and str(dev.get('USB Serial Number', '')).lower() == mac:
        found += [p for p in callouts(dev) if p.startswith('/dev/cu.')]
if len(found) != 1:
    sys.exit(f'test P4 not found uniquely ({len(found)} matches)')
print(found[0])
