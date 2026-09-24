#!/usr/bin/env python3
"""Tests for the network-stream timeout parameter and honest play verify.

Covers two defects found while diagnosing IPTV streams that never started:
 1. A starved rtp://udp:// stream wedged mpv's demuxer open forever (mpv has
    no built-in read timeout for the RTP protocol; --network-timeout only
    reaches HTTP) and leaked the stream's RTP/RTCP sockets, poisoning later
    channel loads. Fix: aiplayer appends FFmpeg's `timeout` URL parameter so
    a dead stream aborts in ~7s instead of never.
 2. play_url reported "Playing: <ch>" as soon as mpv accepted the loadfile,
    even when the stream never started. Fix: optional verify= polls the IPC
    briefly and reports a `playing` bool, with no cause guessing.

Pure-function cases run anywhere; the live-mpv case skips without mpv.
"""
import io, os, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import shutil

from aiplayer.local_player import MpvPlayer, append_stream_timeout, _STREAM_TIMEOUT_US


def main():
    passed = failed = 0

    def check(name, cond, detail=''):
        nonlocal passed, failed
        if cond:
            passed += 1
            print('  PASS %s' % name)
        else:
            failed += 1
            print('  FAIL %s %s' % (name, detail))

    # --- append_stream_timeout: URL forms ---------------------------------
    check('bare rtp URL gets ?timeout',
          append_stream_timeout('rtp://239.94.0.31:5140')
          == 'rtp://239.94.0.31:5140?timeout=%d' % _STREAM_TIMEOUT_US,
          append_stream_timeout('rtp://239.94.0.31:5140'))
    check('udp scheme covered too',
          append_stream_timeout('udp://239.94.0.31:5140')
          == 'udp://239.94.0.31:5140?timeout=%d' % _STREAM_TIMEOUT_US,
          append_stream_timeout('udp://239.94.0.31:5140'))
    check('existing query gets & separator',
          append_stream_timeout('rtp://239.94.0.31:5140?fcc=1')
          == 'rtp://239.94.0.31:5140?fcc=1&timeout=%d' % _STREAM_TIMEOUT_US,
          append_stream_timeout('rtp://239.94.0.31:5140?fcc=1'))
    check('already has timeout -> unchanged (idempotent)',
          append_stream_timeout('rtp://239.94.0.31:5140?timeout=5000000')
          == 'rtp://239.94.0.31:5140?timeout=5000000')
    check('http URL untouched',
          append_stream_timeout('http://192.168.100.10:4022/rtp/239.94.0.31:5140')
          == 'http://192.168.100.10:4022/rtp/239.94.0.31:5140')
    check('local file path untouched',
          append_stream_timeout(r'D:\media\movie.mkv')
          == r'D:\media\movie.mkv')
    check('non-string untouched',
          append_stream_timeout(None) is None)
    check('custom timeout_us honored',
          append_stream_timeout('rtp://239.1.1.1:5000', timeout_us=1234)
          == 'rtp://239.1.1.1:5000?timeout=1234')

    # --- play(): loadfile URL rewriting + verify plumbing ------------------
    def make_player():
        # mpv_path given -> no PATH lookup needed for these unit checks.
        p = MpvPlayer(mpv_path='mpv')
        p._ensure_running = lambda: True
        return p

    p = make_player()
    captured = []
    p._cmd = lambda cmd: (captured.append(cmd), {'error': 'success'})[1]
    p.play('rtp://239.94.0.31:5140')
    check('play rewrites rtp loadfile URL',
          captured[0] == ['loadfile', 'rtp://239.94.0.31:5140?timeout=%d' % _STREAM_TIMEOUT_US, 'replace'],
          str(captured[0]))
    check('play still unpauses after loadfile',
          captured[1] == ['set_property', 'pause', False], str(captured[1]))

    captured.clear()
    p.play(r'D:\media\movie.mkv')
    check('play leaves local file path unchanged',
          captured[0] == ['loadfile', r'D:\media\movie.mkv', 'replace'], str(captured[0]))

    captured.clear()
    p._wait_playing = lambda timeout=3.0, interval=0.3: True
    r = p.play('rtp://239.94.0.31:5140', verify=True)
    check('verify=True reports playing=True',
          r.get('playing') is True, str(r))

    p._wait_playing = lambda timeout=3.0, interval=0.3: False
    r = p.play('rtp://239.94.0.31:5140', verify=True)
    check('verify=True reports playing=False',
          r.get('playing') is False, str(r))

    p._wait_playing = lambda timeout=3.0, interval=0.3: True
    r = p.play('rtp://239.94.0.31:5140')
    check('verify=False omits playing key',
          'playing' not in r, str(r))

    # --- _wait_playing(): scripted IPC replies -----------------------------
    def scripted(timepos_reply, idle_reply):
        p2 = make_player()
        state = {'n': 0}

        def fake(cmd):
            prop = cmd[1] if len(cmd) > 1 else ''
            if prop == 'time-pos':
                return timepos_reply
            if prop == 'idle-active':
                state['n'] += 1
                # First call happens while `first` skips the idle check, so
                # the scripted sequence starts at pass two.
                return idle_reply[min(state['n'] - 1, len(idle_reply) - 1)]
            return {'error': 'success'}

        p2._cmd = fake
        return p2

    pw = scripted({'error': 'success', 'data': 1.5}, [{'error': 'success', 'data': False}])
    check('wait_playing: time-pos present -> True',
          pw._wait_playing(timeout=2.0) is True)

    pw = scripted(timepos_reply={'error': 'property unavailable'},
                  idle_reply=[{'error': 'success', 'data': True}])
    check('wait_playing: load aborted to idle -> False',
          pw._wait_playing(timeout=2.0) is False)

    # Regression pin: the state property must be `idle-active`. `idle` is the
    # --idle OPTION (always true for our persistent player) and would make
    # every verify report "not playing".
    p3 = make_player()
    seen = []
    p3._cmd = lambda cmd: (seen.append(cmd), {'error': 'property unavailable'})[1]
    p3._wait_playing(timeout=0.3, interval=0.1)
    check('wait_playing polls idle-active (not the idle option)',
          any(c[:2] == ['get_property', 'idle-active'] for c in seen)
          and not any(c[:2] == ['get_property', 'idle'] for c in seen), str(seen))

    pw = scripted({'error': 'property unavailable'},
                  [{'error': 'success', 'data': False}])
    t0 = time.time()
    check('wait_playing: no start within timeout -> False',
          pw._wait_playing(timeout=0.5, interval=0.1) is False)
    check('wait_playing timeout honors budget',
          0.4 <= time.time() - t0 < 2.0, '%.2fs' % (time.time() - t0))

    # --- real mpv: dead multicast must fail honestly, and quickly ---------
    if shutil.which('mpv'):
        pr = MpvPlayer()
        t0 = time.time()
        r = pr.play('rtp://239.94.99.99:5140', verify=True)  # unassigned group
        dt = time.time() - t0
        check('dead stream: playing=False within budget',
              r.get('playing') is False and dt < 20,
              'playing=%r dt=%.1fs' % (r.get('playing'), dt))
        pr.stop()  # abort the probe / terminate the spawned mpv
        time.sleep(0.5)
    else:
        print('  SKIP live-mpv dead-stream case (mpv not on PATH)')

    print()
    print('TOTAL: %d passed, %d failed' % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
