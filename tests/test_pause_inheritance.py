#!/usr/bin/env python3
"""Regression test: an externally paused mpv must not swallow play requests.

mpv keeps the `pause` property across file loads, so after a paused session
`aiplayer music ...` used to load the new queue frozen at 0:00: status showed
"Playing", time never advanced, no sound - only `aiplayer play` helped.
play()/playlist_play_index() now force pause=false on every explicit play
request. Requires a real mpv on PATH; skips silently when unavailable.
"""
import io, os, sys, math, shutil, struct, subprocess, tempfile, time, wave

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from aiplayer.local_player import MpvPlayer, MPV_IPC_PATH


def kill_ours():
    """Kill only mpv instances launched with our IPC endpoint (leftovers)."""
    if sys.platform == "win32":
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='mpv.exe'\" | "
              "Where-Object { $_.CommandLine -and $_.CommandLine -like '*mpv-pipe*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, errors="replace")
    else:
        import glob as _glob
        for cmdf in _glob.glob("/proc/[0-9]*/cmdline"):
            try:
                with open(cmdf, "rb") as f:
                    cl = f.read()
                if MPV_IPC_PATH.encode() in cl:
                    os.kill(int(cmdf.split("/")[2]), 9)
            except (OSError, ValueError, IndexError):
                pass
    time.sleep(0.5)


def make_wav(path, seconds=4, freq=440):
    rate = 8000
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def wait_until(fn, timeout=3.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def prop(p, name):
    r = p._cmd(["get_property", name])
    return r.get("data") if r.get("error") in (None, "success") else None


def main():
    if not shutil.which("mpv"):
        print("SKIP: mpv not found on PATH")
        return 0
    tmp = tempfile.mkdtemp(prefix="aiplayer_pause_test_")
    wav1 = os.path.join(tmp, "a.wav")
    wav2 = os.path.join(tmp, "b.wav")
    make_wav(wav1)
    make_wav(wav2, freq=660)

    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print("  PASS %s" % name)
        else:
            failed += 1
            print("  FAIL %s %s" % (name, detail))

    kill_ours()
    try:
        p = MpvPlayer()

        # 1) external pause left behind by a previous session (`aiplayer pause`)
        r1 = p.play(wav1)
        check("first play ok", r1.get("error") in (None, "success"), str(r1))
        check("first play unpaused + advancing",
              wait_until(lambda: prop(p, "pause") is False and prop(p, "core-idle") is False))
        p.set_pause(True)
        check("externally paused", wait_until(lambda: prop(p, "pause") is True))

        # 2) explicit play request must actually play (the reported bug)
        r2 = p.play(wav2)
        check("play after pause ok", r2.get("error") in (None, "success"), str(r2))
        check("play resets inherited pause",
              wait_until(lambda: prop(p, "pause") is False))
        check("playback advancing after play",
              wait_until(lambda: prop(p, "core-idle") is False and (prop(p, "time-pos") or 0) > 0))

        # 3) playlist_play_index also resumes (playfiles-style jump)
        p.set_pause(True)
        r3 = p.playlist_play_index(0)
        check("playlist_play_index ok", r3.get("error") in (None, "success"), str(r3))
        check("playlist_play_index resets pause",
              wait_until(lambda: prop(p, "pause") is False))

        # 4) loadfile replace resets the playlist - no stale entry at index 0
        st = p.status()
        check("status exposes pause flag", st.get("pause") is False, str(st.get("pause")))
        check("playlist exactly one entry", prop(p, "playlist-count") == 1,
              str(prop(p, "playlist-count")))
        check("status reports current file", st.get("filename") == "b.wav",
              str(st.get("filename")))
    finally:
        try:
            MpvPlayer().stop()
        except Exception:
            pass
        kill_ours()

    print()
    print("TOTAL: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
