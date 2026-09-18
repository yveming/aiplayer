#!/usr/bin/env python3
"""Opt-in repro/regression test for the mpv 0.41 PipeWire exit hang.

Enable with:
    AI_PLAYER_MPV_HANG_REPRO=1 python tests/test_mpv_hang_repro.py

It launches aiplayer's mpv headless (display env stripped), plays two video
files (two loadfile replace), then stops and checks whether mpv had to be
force-killed. While the upstream hang exists it FAILs; once quit works
(upstream fix or a workaround) it PASSes and can gate CI.

This is intentionally NOT part of tests/run_all.py: it needs video files and
a real mpv, and its outcome depends on the upstream mpv/PipeWire bug.

Video files: set AI_PLAYER_HANG_M1 / AI_PLAYER_HANG_M2, otherwise the known
local test paths are used when present.
"""
import io, os, sys, glob, shutil, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from aiplayer import local_player as lp
from aiplayer.local_player import MpvPlayer, MPV_IPC_PATH

DEFAULT_M1 = ('/mnt/media/movie/007/'
              'Casino.Royale.2006.CE.Bluray.1080p.DTS-HD.x264-Grym.mkv')
DEFAULT_M2 = ('/mnt/media/movie/007/'
              'No.Time.To.Die.2021.1080p.AMZN.WEB-DL.DDP5.1.H.264-EVO.mkv')


def enabled():
    return os.environ.get('AI_PLAYER_MPV_HANG_REPRO', '').lower() in ('1', 'true', 'yes')


def kill_ours():
    """Kill only mpv instances launched with our IPC endpoint (leftovers)."""
    for cmdf in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            with open(cmdf, 'rb') as f:
                cl = f.read()
            if MPV_IPC_PATH.encode() in cl:
                os.kill(int(cmdf.split('/')[2]), 9)
        except (OSError, ValueError, IndexError):
            pass
    time.sleep(0.5)


def strip_display_env():
    return {k: v for k, v in os.environ.items()
            if k not in ('DISPLAY', 'WAYLAND_DISPLAY')}


def main():
    if not enabled():
        print('SKIP: set AI_PLAYER_MPV_HANG_REPRO=1 to run (spawns real mpv)')
        return 0
    if not shutil.which('mpv'):
        print('SKIP: mpv not found on PATH')
        return 0

    m1 = os.environ.get('AI_PLAYER_HANG_M1', DEFAULT_M1)
    m2 = os.environ.get('AI_PLAYER_HANG_M2', DEFAULT_M2)
    if not (os.path.isfile(m1) and os.path.isfile(m2)):
        print('SKIP: video files not found (set AI_PLAYER_HANG_M1/M2)')
        return 0

    passed = failed = 0

    def check(name, cond, detail=''):
        nonlocal passed, failed
        if cond:
            passed += 1
            print('  PASS %s' % name)
        else:
            failed += 1
            print('  FAIL %s %s' % (name, detail))

    escalated = {'v': False}
    orig_terminate = MpvPlayer._terminate_pid

    def spy_terminate(self, pid):
        escalated['v'] = True
        return orig_terminate(self, pid)

    orig_env = lp._mpv_env
    MpvPlayer._terminate_pid = spy_terminate
    lp._mpv_env = strip_display_env

    kill_ours()
    try:
        p = MpvPlayer()
        r1 = p.play(m1)
        check('play video 1 ok', r1.get('error') in (None, 'success'), str(r1))
        time.sleep(2.0)

        r2 = p.play(m2)
        check('play video 2 (replace) ok', r2.get('error') in (None, 'success'), str(r2))
        time.sleep(2.0)

        t0 = time.time()
        r0 = p.stop()
        dt = time.time() - t0
        check('stop returned', r0.get('error') in (None, 'success'), str(r0))
        check('quit did not need force-kill', not escalated['v'],
              'needed force-kill; stop took %.2fs (upstream mpv PipeWire exit hang)' % dt)
    finally:
        MpvPlayer._terminate_pid = orig_terminate
        lp._mpv_env = orig_env
        kill_ours()

    print()
    print('TOTAL: %d passed, %d failed' % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
