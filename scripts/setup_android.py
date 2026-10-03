#!/usr/bin/env python3
"""Install the Android toolchain for Tiny Clinic, with a live progress bar.

    python3 scripts/setup_android.py plan                    # packages, sizes, licenses
    python3 scripts/setup_android.py brew                    # cmake, command-line tools, Android Studio
    python3 scripts/setup_android.py sdk --accept-licenses   # SDK packages, emulator image, AVD, boot test

Progress goes to data/progress/android-1-brew.txt and android-2-sdk.txt
(live page: python3 scripts/progress.py serve). Download progress is read from
the network counters and measured against each download's published size.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progress import PROGRESS_DIR, Progress  # noqa: E402

SDK_ROOT = Path.home() / "Library" / "Android" / "sdk"
STUDIO_APP = Path("/Applications/Android Studio.app")
STUDIO_JBR = STUDIO_APP / "Contents" / "jbr" / "Contents" / "Home"
AVD_NAME = "tinyclinic"
AVD_RAM_MB = 3072  # simulate a low-end phone
SYSTEM_IMAGE = "system-images;android-34;google_apis;arm64-v8a"
# Versions follow llama.cpp/examples/llama.android, with the stable r29 NDK.
SDK_PACKAGES = [
    "cmdline-tools;latest",
    "platform-tools",
    "platforms;android-36",
    "build-tools;36.0.0",
    "cmake;3.31.6",
    "emulator",
    "ndk;29.0.14206865",
    SYSTEM_IMAGE,
]
REPO_XML = [
    "https://dl.google.com/android/repository/repository2-3.xml",
    "https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml",
]
BREW_ENV = {"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_INSTALL_CLEANUP": "1",
            "HOMEBREW_NO_ENV_HINTS": "1", "NONINTERACTIVE": "1"}


def net_rx_bytes():
    """Bytes received on physical interfaces (en*), from the link-level rows of netstat."""
    out = subprocess.run(["netstat", "-ib"], capture_output=True, text=True).stdout
    total = 0
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 10 and parts[0].startswith("en") and parts[2].startswith("<Link#"):
            total += int(parts[-5])
    return total


def run_step(cmd, log_path, bar, base, size, label, env=None, stdin_text=None):
    """Run one install command; the bar follows bytes received, capped below the step's size."""
    start_rx = net_rx_bytes()
    with open(log_path, "a") as log:
        log.write(f"\n$ {' '.join(map(str, cmd))}\n")
        log.flush()
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, env=env,
                                stdin=subprocess.PIPE if stdin_text else subprocess.DEVNULL)
        if stdin_text:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        while proc.poll() is None:
            got = net_rx_bytes() - start_rx
            bar.update(base + min(got, size * 0.99), label)
            time.sleep(1)
    return proc.returncode


def head_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length", 0))


def cask_size(token, fallback):
    try:
        info = json.loads(subprocess.run(["brew", "info", "--cask", "--json=v2", token],
                                         capture_output=True, text=True, check=True).stdout)
        return head_size(info["casks"][0]["url"]) or fallback
    except Exception:
        return fallback


def cask_installed(token):
    return subprocess.run(["brew", "list", "--cask", token], capture_output=True).returncode == 0


def phase_brew():
    log_path = PROGRESS_DIR / "android-1-brew.log"
    steps = [
        ("cmake", ["brew", "install", "cmake"], 25e6, lambda: shutil.which("cmake") is not None),
        ("android-commandlinetools", ["brew", "install", "--cask", "android-commandlinetools"],
         cask_size("android-commandlinetools", 156e6), lambda: cask_installed("android-commandlinetools")),
        ("android-studio", ["brew", "install", "--cask", "android-studio"],
         cask_size("android-studio", 1.51e9), lambda: STUDIO_APP.exists()),
    ]
    bar = Progress("android-1-brew", sum(s[2] for s in steps), unit="bytes", label="starting")
    env = {**os.environ, **BREW_ENV}
    base = 0
    for name, cmd, size, installed in steps:
        if installed():
            base += size
            bar.update(base, f"{name} already installed")
            continue
        if run_step(cmd, log_path, bar, base, size, f"installing {name}", env=env) != 0:
            bar.fail(f"{name} failed, see {log_path}")
            return 1
        base += size
        bar.update(base, f"{name} installed")
    bar.finish("cmake, Android command-line tools and Android Studio installed")
    return 0


def _local(tag):
    return tag.split("}")[-1]


def sdk_plan():
    """(package, download bytes, licenses) for each SDK package, from Google's repository XML."""
    found = {}
    for url in REPO_XML:
        root = ET.fromstring(urllib.request.urlopen(url, timeout=60).read())
        channels = {el.get("id"): el.text for el in root.iter() if _local(el.tag) == "channel"}
        for pkg in root.iter():
            if _local(pkg.tag) != "remotePackage" or pkg.get("path") not in SDK_PACKAGES:
                continue
            refs = [c.get("ref") for c in pkg if _local(c.tag) == "channelRef"]
            if refs and channels.get(refs[0]) != "stable":
                continue
            licenses = [c.get("ref") for c in pkg if _local(c.tag) == "uses-license"]
            for archive in pkg.iter():
                if _local(archive.tag) != "archive":
                    continue
                fields = {_local(el.tag): el.text for el in archive.iter()}
                if fields.get("host-os") in (None, "macosx") and fields.get("host-arch") in (None, "aarch64"):
                    found.setdefault(pkg.get("path"), (int(fields["size"]), licenses))
                    break
    return [(p, *found.get(p, (100e6, ["unknown"]))) for p in SDK_PACKAGES]


def sdk_installed(package):
    return (SDK_ROOT / package.replace(";", "/") / "package.xml").exists()


def tool_env():
    env = {**os.environ, "ANDROID_HOME": str(SDK_ROOT), "ANDROID_SDK_ROOT": str(SDK_ROOT)}
    if STUDIO_JBR.exists():  # Android Studio's bundled JBR (Java 25 in Studio 2026.2)
        env["JAVA_HOME"] = str(STUDIO_JBR)
        env["PATH"] = f"{STUDIO_JBR / 'bin'}:{env['PATH']}"
    return env


def find_sdkmanager():
    local = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
    return str(local) if local.exists() else shutil.which("sdkmanager")


def create_avd(env, log_path):
    avdmanager = SDK_ROOT / "cmdline-tools" / "latest" / "bin" / "avdmanager"
    cmd = [str(avdmanager), "create", "avd", "-n", AVD_NAME, "-k", SYSTEM_IMAGE, "-d", "pixel_6", "--force"]
    with open(log_path, "a") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        rc = subprocess.run(cmd, input="no\n", stdout=log, stderr=subprocess.STDOUT, text=True, env=env).returncode
    if rc != 0:
        return rc
    config = Path.home() / ".android" / "avd" / f"{AVD_NAME}.avd" / "config.ini"
    lines = [l for l in config.read_text().splitlines()
             if not l.startswith(("hw.ramSize", "hw.keyboard", "disk.dataPartition.size"))]
    lines += [f"hw.ramSize={AVD_RAM_MB}", "hw.keyboard=yes", "disk.dataPartition.size=6G"]
    config.write_text("\n".join(lines) + "\n")
    return 0


def boot_test(env, log_path, bar, base, weight, timeout=420):
    """Cold-boot the AVD headless, wait for Android to finish booting, shut it down."""
    emulator = SDK_ROOT / "emulator" / "emulator"
    adb = SDK_ROOT / "platform-tools" / "adb"
    with open(log_path, "a") as log:
        log.write(f"\n$ emulator -avd {AVD_NAME} -no-window (boot test)\n")
        log.flush()
        emu = subprocess.Popen([str(emulator), "-avd", AVD_NAME, "-no-window", "-no-audio", "-no-boot-anim",
                                "-no-snapshot-save", "-gpu", "swiftshader_indirect"],
                               stdout=log, stderr=subprocess.STDOUT, env=env)
    start = time.time()
    booted = False
    while time.time() - start < timeout and emu.poll() is None:
        out = subprocess.run([str(adb), "shell", "getprop", "sys.boot_completed"],
                             capture_output=True, text=True, env=env).stdout.strip()
        if out == "1":
            booted = True
            break
        bar.update(base + weight * min(0.95, (time.time() - start) / 120), "boot test: emulator starting")
        time.sleep(3)
    seconds = time.time() - start
    subprocess.run([str(adb), "emu", "kill"], capture_output=True, env=env)
    try:
        emu.wait(timeout=60)
    except subprocess.TimeoutExpired:
        emu.kill()
    return booted, seconds


def phase_sdk(accept_licenses):
    log_path = PROGRESS_DIR / "android-2-sdk.log"
    plan = sdk_plan()
    downloads = sum(size for _, size, _ in plan)
    avd_weight = downloads * 0.05
    bar = Progress("android-2-sdk", downloads + avd_weight, unit="bytes", label="starting")
    if not accept_licenses:
        licenses = sorted({l for _, _, ls in plan for l in ls})
        bar.pause("waiting for license approval: " + ", ".join(licenses))
        return 2
    env = tool_env()
    SDK_ROOT.mkdir(parents=True, exist_ok=True)
    base = 0
    for package, size, _ in plan:
        if sdk_installed(package):
            base += size
            bar.update(base, f"{package} already installed")
            continue
        sdkmanager = find_sdkmanager()
        if not sdkmanager:
            bar.fail("sdkmanager not found; run the brew phase first")
            return 1
        cmd = [sdkmanager, f"--sdk_root={SDK_ROOT}", "--install", package]
        # Accepts only the licenses these packages use, as approved by the user.
        if run_step(cmd, log_path, bar, base, size, package, env=env, stdin_text="y\n" * 20) != 0 \
                or not sdk_installed(package):
            bar.fail(f"{package} failed, see {log_path}")
            return 1
        base += size
        bar.update(base, f"{package} installed")
    bar.update(base, "creating emulator")
    if create_avd(env, log_path) != 0:
        bar.fail(f"AVD creation failed, see {log_path}")
        return 1
    booted, seconds = boot_test(env, log_path, bar, base, avd_weight)
    if not booted:
        bar.fail(f"emulator did not finish booting in {seconds:.0f}s, see {log_path}")
        return 1
    bar.finish(f"SDK ready; emulator '{AVD_NAME}' ({AVD_RAM_MB} MB RAM) cold-booted in {seconds:.0f}s")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("brew")
    s = sub.add_parser("sdk")
    s.add_argument("--accept-licenses", action="store_true",
                   help="accept the licenses of the listed SDK packages (only with the user's approval)")
    args = parser.parse_args()
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    if args.cmd == "plan":
        plan = sdk_plan()
        for package, size, licenses in plan:
            print(f"{package:48s} {size / 1e6:8.1f} MB  {', '.join(licenses)}")
        print(f"{'total':48s} {sum(s for _, s, _ in plan) / 1e9:8.2f} GB")
        return 0
    if args.cmd == "brew":
        return phase_brew()
    return phase_sdk(args.accept_licenses)


if __name__ == "__main__":
    sys.exit(main())
