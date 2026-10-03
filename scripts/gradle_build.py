#!/usr/bin/env python3
"""Run a Gradle build of the Android app with live progress bars.

    python3 scripts/gradle_build.py                       # :app:assembleDebug
    python3 scripts/gradle_build.py :app:installDebug

Two bars (live page: python3 scripts/progress.py serve):
  android-setup  a dry run that counts the tasks; the first time it also downloads
                 Gradle, the Android plugin and the libraries
  android-build  the real build: one step per Gradle task plus one per native compile
                 step of llama.cpp
Full output goes to data/progress.nosync/android-build.log.
"""

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progress import PROGRESS_DIR, Progress  # noqa: E402
from setup_android import SDK_ROOT, STUDIO_JBR, net_rx_bytes  # noqa: E402

ANDROID_DIR = Path(__file__).resolve().parent.parent / "android"
LOG_PATH = PROGRESS_DIR / "android-build.log"
FIRST_RUN_BYTES = 700e6   # Gradle, AGP, Kotlin, Compose and friends: first run only
NATIVE_STEPS_GUESS = 450  # llama.cpp compile steps, until ninja reports the real count
DRY_RUN_TASK = re.compile(r"^(:\S+) SKIPPED$")
TASK = re.compile(r"^> Task (:\S+)(?: (\S+))?")
NINJA = re.compile(r"\[(\d+)/(\d+)\]")


def gradle_env():
    env = {**os.environ, "ANDROID_HOME": str(SDK_ROOT), "ANDROID_SDK_ROOT": str(SDK_ROOT)}
    env["JAVA_HOME"] = str(STUDIO_JBR)
    env["PATH"] = f"{STUDIO_JBR / 'bin'}:{env['PATH']}"
    return env


def run(args, log, on_line):
    """Run ./gradlew with `args`, send every line to the log and to on_line; return the exit code."""
    log.write(f"\n$ ./gradlew {' '.join(args)}\n")
    log.flush()
    proc = subprocess.Popen(["./gradlew", *args, "--console=plain", "--project-cache-dir", ".gradle.nosync"], cwd=ANDROID_DIR, env=gradle_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        log.write(line)
        on_line(line.rstrip("\n"))
    log.flush()
    return proc.wait()


def every_second(update, stop):
    while not stop.is_set():
        update()
        stop.wait(1)


def tail_errors(n=40):
    lines = LOG_PATH.read_text(errors="replace").splitlines()
    marked = [i for i, l in enumerate(lines) if re.search(r"error|FAILURE|What went wrong|Exception", l, re.I)]
    start = max(0, (marked[0] - 5) if marked else len(lines) - n)
    return "\n".join(lines[start:start + n])


def main():
    tasks = sys.argv[1:] or [":app:assembleDebug"]
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w") as log:
        # 1. Dry run: count the tasks (and download everything the first time).
        setup = Progress("android-setup", total=FIRST_RUN_BYTES, unit="bytes", label="dry run")
        start_rx, planned, stop = net_rx_bytes(), [], threading.Event()

        def update_setup():
            got = net_rx_bytes() - start_rx
            setup.update(min(got, FIRST_RUN_BYTES * 0.99), f"dry run: {len(planned)} tasks found")

        ticker = threading.Thread(target=every_second, args=(update_setup, stop), daemon=True)
        ticker.start()
        code = run([*tasks, "-m"], log, lambda l: (m := DRY_RUN_TASK.match(l)) and planned.append(m.group(1)))
        stop.set()
        ticker.join()
        if code != 0:
            setup.fail(f"dry run failed, see {LOG_PATH}")
            print(tail_errors())
            return code
        downloaded = max(net_rx_bytes() - start_rx, 1)
        setup.update(total=downloaded)  # the bar ends at what was really downloaded
        setup.finish(f"{len(planned)} tasks planned, {downloaded / 1e6:.0f} MB downloaded")

        # 2. The build: Gradle tasks plus the native compile steps.
        state = {"done": set(), "native": [0, NATIVE_STEPS_GUESS], "native_done": False, "task": "starting"}
        build = Progress("android-build", total=len(planned) + NATIVE_STEPS_GUESS, label="starting")

        def on_line(line):
            if m := TASK.match(line):
                state["done"].add(m.group(1))
                state["task"] = m.group(1)
                if "buildCMake" in m.group(1) and m.group(2) in ("UP-TO-DATE", "FROM-CACHE"):
                    state["native_done"] = True
            elif m := NINJA.search(line):
                state["native"] = [int(m.group(1)), int(m.group(2))]

        def update_build():
            n, total_native = state["native"]
            if state["native_done"]:
                n = total_native
            build.update(min(len(state["done"]), len(planned)) + n, total=len(planned) + total_native,
                         label=f"tasks {len(state['done'])}/{len(planned)}, native {n}/{total_native}: {state['task']}")

        stop = threading.Event()
        ticker = threading.Thread(target=every_second, args=(update_build, stop), daemon=True)
        ticker.start()
        code = run(tasks, log, on_line)
        stop.set()
        ticker.join()
        if code != 0:
            build.fail(f"build failed at {state['task']}, see {LOG_PATH}")
            print(tail_errors())
            return code
        build.finish(f"{' '.join(tasks)} done: {len(state['done'])} tasks")
        print(f"BUILD OK: {' '.join(tasks)}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
