#!/usr/bin/env python3
"""Diagnose mpv hanging on quit after a second loadfile (aiplayer flow).

Linux only. Spawns mpv like aiplayer does, replays wire sequences, and
autopsies a survivor (per-thread names/states, ss, mpv log tail).

Usage:
    python3 tests/archive/diag_mpv_stop_hang.py <media1> [media2]

Arguments may be media files or release directories (first media file
inside is picked). Sequences (fresh mpv each):
  A: [m1] quit
  B: [m1] stop quit
  C: [m1,m2] stop quit          (failing CLI flow)
  D: [m1,m2] quit               (no stop)
  E: [m2] quit                  (media2 alone)
  F: [m1,m2] quit --no-config   (disable user scripts/config)
  G: [m2] quit --no-config
"""
import glob
import json
import os
import signal
import socket
import subprocess
import sys
import time

MPV = "mpv"

MEDIA_EXTS = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv",
              ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".iso", ".rmvb")


def _pick(directory, prefix=None):
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    for f in names:
        if prefix and not f.startswith(prefix):
            continue
        p = os.path.join(directory, f)
        if f.lower().endswith(MEDIA_EXTS) and os.path.isfile(p):
            return p
    return None


def resolve_media(path):
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        return _pick(path)
    parent = os.path.dirname(path) or "."
    return _pick(parent, prefix=os.path.basename(path))


def ipc(cmd, sock, timeout=8.0):
    t0 = time.time()
    rec = {"cmd": cmd[0] if cmd else "?", "wire": [], "error": None}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock)
        rec["wire"].append(["connect", round(time.time() - t0, 3)])
        s.sendall((json.dumps({"command": cmd}) + "\n").encode())
        rec["wire"].append(["send", round(time.time() - t0, 3)])
        buf = b""
        done = False
        while not done:
            chunk = s.recv(4096)
            if not chunk:
                rec["wire"].append(["EOF", round(time.time() - t0, 3)])
                break
            text = chunk.decode("utf-8", "replace").strip()
            rec["wire"].append([text, round(time.time() - t0, 3)])
            buf += chunk
            for line in buf.decode("utf-8", "replace").split("\n")[:-1]:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and "event" not in obj and "error" in obj:
                    done = True
                    break
    except Exception as e:
        rec["error"] = "%s at +%.3fs" % (type(e).__name__, time.time() - t0)
    finally:
        s.close()
    rec["dt"] = round(time.time() - t0, 3)
    print("  IPC %-16s -> %s" % (rec["cmd"], json.dumps(rec, ensure_ascii=False)))
    return rec


def alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            state = f.read().rsplit(")", 1)[-1].split()[0]
        return state != "Z"
    except OSError:
        return False


def tasks(pid):
    out = []
    for tf in glob.glob("/proc/%d/task/*/stat" % pid):
        try:
            data = open(tf).read()
        except OSError:
            continue
        comm = data.split("(", 1)[1].rsplit(")", 1)[0]
        state = data.rsplit(")", 1)[-1].split()[0]
        out.append((comm, state))
    return out


def spawn(sock, log, no_config=False, ao=None):
    args = [MPV, "--idle=yes", "--keep-open=yes",
            "--input-ipc-server=%s" % sock, "--no-terminal",
            "--log-file=%s" % log]
    if no_config:
        args.append("--no-config")
    if ao:
        args.append("--ao=%s" % ao)
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < 5:
        r = ipc(["get_property", "idle"], sock, timeout=2)
        if r["error"] is None:
            tag = (" [--no-config]" if no_config else "") + (" [--ao=%s]" % ao if ao else "")
            print("  mpv ready pid=%d%s" % (p.pid, tag))
            return p
        time.sleep(0.2)
    raise RuntimeError("mpv IPC never became ready")


def watch_exit(p, seconds=10):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if not alive(p.pid):
            print("  mpv exited after %.1fs  OK" % (time.time() - t0))
            return True
        time.sleep(0.5)
    print("  mpv STILL ALIVE after %ds  <-- PROBLEM" % seconds)
    return False


def autopsy(p, sock, log):
    print("  --- autopsy ---")
    print("  socket file exists:", os.path.exists(sock))
    try:
        with open("/proc/%d/status" % p.pid) as f:
            for ln in f:
                if ln.startswith(("State", "Threads")):
                    print("  " + ln.strip())
    except OSError as e:
        print("  /proc read failed:", e)
    print("  threads (name: state):")
    for comm, state in tasks(p.pid):
        print("    %-22s %s" % (comm, state))
    print("  probe (3s cap):")
    ipc(["get_property", "idle"], sock, timeout=3)
    if alive(p.pid):
        try:
            out = subprocess.run(["ss", "-xnp"], capture_output=True,
                                 text=True).stdout
            hits = [ln for ln in out.splitlines() if "mpv" in ln or sock in ln]
            print("  ss -xnp (mpv/socket lines):")
            for ln in hits[:10]:
                print("    " + ln.strip())
        except OSError:
            pass
        os.kill(p.pid, signal.SIGTERM)
        time.sleep(2)
        print("  alive after SIGTERM:", alive(p.pid))
        if alive(p.pid):
            os.kill(p.pid, signal.SIGKILL)
            print("  SIGKILLed")
    if os.path.exists(log):
        print("  --- mpv log tail ---")
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for ln in lines[-18:]:
            print("    " + ln[:200])


def run_seq(name, files, do_stop, no_config=False, ao=None, stop_between=False):
    print("=" * 62)
    flow = "-> ".join(["loadfile"] * len(files)) \
        + (" -> stop" if do_stop else "") + " -> quit"
    if stop_between:
        flow = "loadfile -> stop -> loadfile -> quit"
    tags = ("  [--no-config]" if no_config else "") + ("  [--ao=%s]" % ao if ao else "")
    print("sequence %s: %s%s" % (name, flow, tags))
    subprocess.run(["pkill", "-9", "mpv"], capture_output=True)
    time.sleep(0.5)
    sock = "/tmp/diag-mpv-%s.sock" % name
    log = "/tmp/diag-mpv-%s.log" % name
    p = spawn(sock, log, no_config, ao)
    ipc(["loadfile", files[0], "replace"], sock)
    time.sleep(2)
    if len(files) > 1:
        if stop_between:
            ipc(["stop"], sock)
            time.sleep(1)
        ipc(["loadfile", files[1], "replace"], sock)
        time.sleep(2)
    r = ipc(["get_property", "idle"], sock, timeout=3)
    wire = json.dumps(r["wire"], ensure_ascii=False)
    if '"data":true' in wire:
        print("  *** NOT PLAYING (idle=true) - result not meaningful ***")
    else:
        print("  playing confirmed (idle=false)")
    if do_stop:
        ipc(["stop"], sock)
    ipc(["quit"], sock)
    ok = watch_exit(p, 10)
    if not ok:
        autopsy(p, sock, log)
    if alive(p.pid):
        subprocess.run(["pkill", "-9", "mpv"], capture_output=True)
    time.sleep(0.5)
    print("  result: %s" % ("PASS" if ok else "HANG"))
    return ok


def main():
    if sys.platform == "win32":
        sys.exit("run this on the Linux box")
    if len(sys.argv) < 2:
        sys.exit("usage: diag_mpv_stop_hang.py <media1> [media2]")
    r1 = resolve_media(sys.argv[1])
    r2 = resolve_media(sys.argv[2]) if len(sys.argv) > 2 else r1
    if not r1 or not r2:
        sys.exit("no media file found in: %r / %r" % (
            sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]))
    m1, m2 = r1, r2
    print("media1: %s" % m1)
    if m2 != m1:
        print("media2: %s" % m2)
    out = subprocess.run([MPV, "--version"], capture_output=True, text=True)
    print(out.stdout.splitlines()[0] if out.stdout else "mpv version unknown")
    results = []
    results.append(("C", run_seq("C", [m1, m2], True)))
    results.append(("H", run_seq("H", [m1, m2], False, stop_between=True)))
    results.append(("I", run_seq("I", [m1, m2], False, ao="pulse")))
    results.append(("J", run_seq("J", [m1, m2], False, ao="null")))
    print("=" * 62)
    print("summary: " + "  ".join(
        "%s=%s" % (n, "PASS" if ok else "HANG") for n, ok in results))
    print("done. paste this whole output back.")


if __name__ == "__main__":
    main()
