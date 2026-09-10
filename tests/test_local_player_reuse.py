#!/usr/bin/env python3
"""Regression test: repeated playback must NOT spawn extra mpv processes.

Fresh MpvPlayer instances simulate successive CLI invocations (each starts
with _running=False, same code path as a new aiplayer process). Requires a
real mpv on PATH; skips silently when unavailable.
"""
import io, os, sys, glob, math, shutil, struct, subprocess, tempfile, time, wave

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from aiplayer.local_player import MpvPlayer, MPV_IPC_PATH


def count_mpv():
    if sys.platform == 'win32':
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq mpv.exe',
                            '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace')
        return sum(1 for ln in (r.stdout or '').splitlines()
                   if ln.strip().upper().startswith('"MPV.EXE"'))
    r = subprocess.run(['pgrep', '-x', 'mpv'], capture_output=True, text=True, errors='replace')
    if r.returncode != 0:
        return 0
    return len([ln for ln in (r.stdout or '').splitlines() if ln.strip()])


def kill_ours():
    """Kill only mpv instances launched with our IPC endpoint (leftovers)."""
    if sys.platform == 'win32':
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='mpv.exe'\" | "
              "Where-Object { $_.CommandLine -and $_.CommandLine -like '*mpv-pipe*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, errors='replace')
    else:
        for cmdf in glob.glob('/proc/[0-9]*/cmdline'):
            try:
                with open(cmdf, 'rb') as f:
                    cl = f.read()
                if MPV_IPC_PATH.encode() in cl:
                    os.kill(int(cmdf.split('/')[2]), 9)
            except (OSError, ValueError, IndexError):
                pass
    time.sleep(0.5)


def make_wav(path, seconds=2, freq=440):
    rate = 8000
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            v = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack('<h', v)
        w.writeframes(bytes(frames))


def main():
    if not shutil.which('mpv'):
        print('SKIP: mpv not found on PATH')
        return 0
    tmp = tempfile.mkdtemp(prefix='aiplayer_mpv_test_')
    wav1 = os.path.join(tmp, 'a.wav')
    wav2 = os.path.join(tmp, 'b.wav')
    make_wav(wav1)
    make_wav(wav2, freq=660)

    passed = failed = 0

    def check(name, cond, detail=''):
        nonlocal passed, failed
        if cond:
            passed += 1
            print('  PASS %s' % name)
        else:
            failed += 1
            print('  FAIL %s %s' % (name, detail))

    kill_ours()
    before = count_mpv()

    p1 = MpvPlayer()
    r1 = p1.play(wav1)
    check('first play ok', r1.get('error') in (None, 'success'), str(r1))
    time.sleep(0.3)
    after_first = count_mpv()
    check('one mpv spawned on first play', after_first == before + 1,
          'before=%d after=%d' % (before, after_first))

    del p1
    time.sleep(0.5)
    p2 = MpvPlayer()
    r2 = p2.play(wav2)
    check('second play ok (reused, no new mpv)', r2.get('error') in (None, 'success'), str(r2))
    time.sleep(0.5)
    after_second = count_mpv()
    check('mpv process count stable across plays', after_second == after_first,
          'first=%d second=%d' % (after_first, after_second))

    st = p2.status()
    check('status reports second file', st.get('filename') == 'b.wav',
          str(st.get('filename')))

    r0 = p2.stop()
    check('stop returns success', r0.get('error') == 'success', str(r0))
    time.sleep(0.5)
    ended = count_mpv()
    check('stop terminates spawned mpv', ended == before,
          'before=%d ended=%d' % (before, ended))

    r3 = p2.stop()
    check('stop when not running does not spawn', r3.get('error') == 'not running', str(r3))
    ended2 = count_mpv()
    check('mpv count unchanged after extra stop', ended2 == ended,
          'ended=%d now=%d' % (ended, ended2))

    r4 = p2.play_pause()
    check('control on dead mpv does not spawn', r4.get('error') == 'not running', str(r4))
    ended3 = count_mpv()
    check('mpv count unchanged after control on dead mpv', ended3 == ended,
          'ended=%d now=%d' % (ended, ended3))

    p3 = MpvPlayer()
    r5 = p3.play(wav1)
    check('play after stop respawns mpv', r5.get('error') in (None, 'success'), str(r5))
    time.sleep(0.3)
    respawned = count_mpv()
    check('exactly one mpv after respawn', respawned == ended + 1,
          'ended=%d now=%d' % (ended, respawned))
    p3.stop()
    time.sleep(0.5)
    final = count_mpv()
    check('final stop terminates again', final == before,
          'before=%d now=%d' % (before, final))

    p4 = MpvPlayer()
    p4.play(wav1)
    p4.play(wav2)
    r6 = p4.stop()
    check('stop after play+replace success', r6.get('error') in (None, 'success'), str(r6))
    time.sleep(0.5)
    after_replace = count_mpv()
    check('stop after play+replace terminates mpv', after_replace == before,
          'before=%d now=%d' % (before, after_replace))

    if sys.platform != 'win32':
        victim = subprocess.Popen(['sleep', '30'])
        MpvPlayer()._terminate_pid(victim.pid)
        time.sleep(0.4)
        check('escalation kills a stuck process', victim.poll() is not None,
              'pid=%d' % victim.pid)
        if victim.poll() is None:
            victim.kill()

    print()
    print('TOTAL: %d passed, %d failed' % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
