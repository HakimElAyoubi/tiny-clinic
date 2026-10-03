#!/usr/bin/env python3
"""Progress bars for long jobs, with a live page.

Each job writes its state to data/progress.nosync/<job>.json and a one-line bar to
data/progress.nosync/<job>.txt:

    [########------------]  40%  2.0/5.0 GB  elapsed 03:12  ETA 04:48  ndk;29.0.14206865

From Python:
    from progress import Progress
    bar = Progress("fetch-data", total=12)
    bar.update(3, "tokenizers")
    bar.finish()

From a shell:
    python3 scripts/progress.py set fetch-data 3 12 "tokenizers"

Live page (refreshes itself every second):
    python3 scripts/progress.py serve --port 8765
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# .nosync keeps these fast-changing files out of iCloud, which would make conflict copies.
PROGRESS_DIR = Path(__file__).resolve().parent.parent / "data" / "progress.nosync"
BAR_WIDTH = 20


def fmt_duration(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_count(done, total, unit):
    if unit == "bytes":
        scale, suffix = (1e9, "GB") if total >= 1e9 else (1e6, "MB")
        return f"{done / scale:.2f}/{total / scale:.2f} {suffix}"
    return f"{int(done)}/{int(total)}"


def render(state, now=None):
    """One-line bar. Elapsed and ETA are computed at `now` while running."""
    now = now or time.time()
    total = state["total"] or 0
    done = min(state["done"], total) if total else state["done"]
    frac = done / total if total else 0.0
    filled = int(round(frac * BAR_WIDTH))
    bar = "[" + "#" * filled + "-" * (BAR_WIDTH - filled) + "]"
    status = state["status"]
    end = now if status == "running" else state["updated"]
    elapsed = end - state["started"]
    if status == "done":
        eta = "done"
    elif status in ("failed", "paused"):
        eta = status.upper()
    elif done > 0 and elapsed > 0:
        eta = "ETA " + fmt_duration((total - done) / (done / elapsed))
    else:
        eta = "ETA --:--"
    count = fmt_count(done, total, state.get("unit", ""))
    return f"{bar} {frac * 100:3.0f}%  {count}  elapsed {fmt_duration(elapsed)}  {eta}  {state.get('label', '')}".rstrip()


def _write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class Progress:
    def __init__(self, job, total, unit="", label="", directory=PROGRESS_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        self.state = {"job": job, "done": 0, "total": total, "unit": unit, "label": label,
                      "status": "running", "started": now, "updated": now}
        self._write()

    def update(self, done=None, label=None, total=None, status=None):
        if done is not None:
            self.state["done"] = done
        if label is not None:
            self.state["label"] = label
        if total is not None:
            self.state["total"] = total
        if status is not None:
            self.state["status"] = status
        self.state["updated"] = time.time()
        self._write()

    def finish(self, label=None):
        self.update(done=self.state["total"], label=label, status="done")

    def fail(self, label):
        self.update(label=label, status="failed")

    def pause(self, label):
        self.update(label=label, status="paused")

    def _write(self):
        job = self.state["job"]
        _write_atomic(self.dir / f"{job}.json", json.dumps(self.state))
        _write_atomic(self.dir / f"{job}.txt", render(self.state) + "\n")


def load_states(directory=PROGRESS_DIR):
    states = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            states.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(states, key=lambda s: s["started"])


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tiny Clinic jobs</title>
<style>
:root { --bg:#f7f7f5; --card:#fff; --fg:#1d1d1b; --muted:#6b6b66; --track:#e6e6e1;
        --run:#2f6fde; --done:#1f9d55; --fail:#d64545; --pause:#c98a00; }
@media (prefers-color-scheme: dark) { :root { --bg:#151514; --card:#1f1f1d; --fg:#ececea;
        --muted:#9a9a94; --track:#33332f; --run:#6fa0ff; --done:#4cc782; --fail:#ff7a7a; --pause:#f0b93a; } }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
       font:15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width:860px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:var(--muted); margin:0 0 20px; font-size:13px; }
.job { background:var(--card); border-radius:10px; padding:14px 16px; margin-bottom:12px;
       box-shadow:0 1px 2px rgba(0,0,0,.06); }
.head { display:flex; justify-content:space-between; gap:12px; align-items:baseline; }
.name { font-weight:600; }
.pill { font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
.track { height:10px; background:var(--track); border-radius:5px; margin:10px 0 8px; overflow:hidden; }
.fill { height:100%; border-radius:5px; transition:width .6s ease; }
.line { font:12.5px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; color:var(--muted);
        overflow-wrap:anywhere; }
.stale { color:var(--pause); font-size:12px; margin-top:4px; }
.empty { color:var(--muted); }
</style></head>
<body><main>
<h1>Tiny Clinic jobs</h1>
<p class="sub" id="sub">Connecting&hellip;</p>
<div id="jobs"></div>
</main>
<script>
const colors = { running:"var(--run)", done:"var(--done)", failed:"var(--fail)", paused:"var(--pause)" };
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
async function tick() {
  try {
    const r = await fetch("/api", { cache: "no-store" });
    const jobs = await r.json();
    const box = document.getElementById("jobs");
    if (!jobs.length) { box.innerHTML = '<p class="empty">No jobs yet.</p>'; }
    else box.innerHTML = jobs.map(j => {
      const pct = j.total ? Math.min(100, 100 * j.done / j.total) : 0;
      const stale = j.status === "running" && j.age > 120
        ? `<div class="stale">No update for ${Math.round(j.age)}s</div>` : "";
      return `<div class="job"><div class="head"><span class="name">${esc(j.job)}</span>
        <span class="pill" style="color:${colors[j.status] || "var(--muted)"}">${esc(j.status)}</span></div>
        <div class="track"><div class="fill" style="width:${pct.toFixed(1)}%;background:${colors[j.status] || "var(--run)"}"></div></div>
        <div class="line">${esc(j.line)}</div>${stale}</div>`;
    }).join("");
    document.getElementById("sub").textContent = "Live, refreshes every second. Last refresh " + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById("sub").textContent = "Server not reachable, retrying...";
  }
}
tick(); setInterval(tick, 1000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    directory = PROGRESS_DIR

    def do_GET(self):
        if self.path.startswith("/api"):
            now = time.time()
            jobs = [{**s, "line": render(s, now), "age": now - s["updated"]} for s in load_states(self.directory)]
            body, ctype = json.dumps(jobs).encode(), "application/json"
        elif self.path in ("/", "/index.html"):
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="write a job's progress from a shell")
    s.add_argument("job")
    s.add_argument("done", type=float)
    s.add_argument("total", type=float)
    s.add_argument("label", nargs="?", default="")
    s.add_argument("--status", default="running", choices=["running", "done", "failed", "paused"])
    s.add_argument("--unit", default="")
    v = sub.add_parser("serve", help="serve the live page")
    v.add_argument("--port", type=int, default=8765)
    sub.add_parser("show", help="print every job's bar once")
    args = parser.parse_args()

    if args.cmd == "set":
        path = PROGRESS_DIR / f"{args.job}.json"
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        state = json.loads(path.read_text()) if path.exists() else {"job": args.job, "started": now}
        state.update(done=args.done, total=args.total, label=args.label, status=args.status,
                     unit=args.unit or state.get("unit", ""), updated=now)
        _write_atomic(path, json.dumps(state))
        _write_atomic(PROGRESS_DIR / f"{args.job}.txt", render(state) + "\n")
    elif args.cmd == "serve":
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Progress page on http://127.0.0.1:{args.port}", flush=True)
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    elif args.cmd == "show":
        for state in load_states():
            print(f"{state['job']:>16}  {render(state)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
