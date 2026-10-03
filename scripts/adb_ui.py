#!/usr/bin/env python3
"""Drive the Tiny Clinic app on the emulator by visible text (for tests and demo recordings).

    python3 scripts/adb_ui.py launch
    python3 scripts/adb_ui.py tap "Check (no model"        # first element whose text starts with this
    python3 scripts/adb_ui.py type 24
    python3 scripts/adb_ui.py shot data/progress.nosync/screen.png
    python3 scripts/adb_ui.py texts                         # every visible text, top to bottom
"""

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
PACKAGE = "org.tinyclinic.app"


def adb(*args, capture=True):
    return subprocess.run([ADB, *args], capture_output=capture, text=True, check=True).stdout


def nodes(editable=False):
    """(text, centre x, centre y) for every element with text (or every input field), top to bottom."""
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    root = ET.fromstring(adb("shell", "cat", "/sdcard/ui.xml"))
    found = []
    for node in root.iter("node"):
        text = node.get("text") or node.get("content-desc") or ""
        if editable:
            text = "input" if node.get("class") == "android.widget.EditText" else ""
        bounds = re.findall(r"\d+", node.get("bounds", ""))
        if text and len(bounds) == 4:
            x1, y1, x2, y2 = map(int, bounds)
            found.append((text, (x1 + x2) // 2, (y1 + y2) // 2))
    return sorted(found, key=lambda n: (n[2], n[1]))


def tap(prefix, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for text, x, y in nodes():
            if text.startswith(prefix):
                adb("shell", "input", "tap", str(x), str(y))
                time.sleep(0.6)
                return text
        time.sleep(1)
    raise SystemExit(f"no element starting with {prefix!r}")


def main():
    cmd, *args = sys.argv[1:] or ["texts"]
    if cmd == "launch":
        adb("shell", "am", "force-stop", PACKAGE)
        adb("shell", "am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")
    elif cmd == "tap":
        print("tapped", tap(args[0]))
    elif cmd == "type":  # into the first input field on screen
        fields = nodes(editable=True)
        if fields:
            adb("shell", "input", "tap", str(fields[0][1]), str(fields[0][2]))
            time.sleep(0.4)
        adb("shell", "input", "text", args[0].replace(" ", "%s"))
        time.sleep(0.4)
    elif cmd == "shot":
        Path(args[0]).write_bytes(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, check=True).stdout)
        print("saved", args[0])
    elif cmd == "texts":
        for text, _, _ in nodes():
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
