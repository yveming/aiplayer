#!/usr/bin/env python3
"""Unit tests for mpv display-environment recovery (local_player).

Covers the fallback that lets an agent daemon (systemd --user service)
launch mpv with the desktop session's DISPLAY/WAYLAND_DISPLAY when the
service started before the session exported them. Offline, no real mpv.
"""
import io
import os
import sys
import types

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from aiplayer import local_player as lp


passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS %s' % name)
    else:
        failed += 1
        print('  FAIL %s %s' % (name, detail))


def boom():
    raise AssertionError('unexpected call')


def main():
    # --- _parse_env_lines ---
    text = ("XDG_RUNTIME_DIR=/run/user/1001\n"
            "DISPLAY=:0\n"
            "WAYLAND_DISPLAY=wayland-0\n"
            "XAUTHORITY=/run/user/1001/.mutter-Xwaylandauth.ABC\n"
            "XDG_SESSION_TYPE=wayland\n"
            "UNRELATED=1\n")
    env = lp._parse_env_lines(text)
    check('parse keeps DISPLAY', env.get('DISPLAY') == ':0', str(env))
    check('parse keeps WAYLAND_DISPLAY', env.get('WAYLAND_DISPLAY') == 'wayland-0')
    check('parse keeps XAUTHORITY',
          env.get('XAUTHORITY') == '/run/user/1001/.mutter-Xwaylandauth.ABC')
    check('parse keeps XDG_SESSION_TYPE', env.get('XDG_SESSION_TYPE') == 'wayland')
    check('parse drops unrelated keys', 'UNRELATED' not in env)

    env2 = lp._parse_env_lines('DISPLAY=\nJUNK\n=1\nWAYLAND_DISPLAY=wayland-0\n')
    check('parse drops empty values', 'DISPLAY' not in env2)
    check('parse keeps later valid key', env2.get('WAYLAND_DISPLAY') == 'wayland-0')
    check('parse handles None', lp._parse_env_lines(None) == {})

    # --- _session_display_env / _mpv_env (monkeypatched) ---
    orig_run = lp.subprocess.run
    orig_which = lp.shutil.which
    orig_proc = lp._env_from_proc
    orig_session = lp._session_display_env
    saved_display = os.environ.get('DISPLAY')
    saved_wl = os.environ.get('WAYLAND_DISPLAY')
    try:
        lp.shutil.which = lambda name: '/usr/bin/systemctl'
        lp.subprocess.run = lambda *a, **k: types.SimpleNamespace(
            stdout='DISPLAY=:0\nWAYLAND_DISPLAY=wayland-0\nXAUTHORITY=/tmp/xauth\n')
        lp._env_from_proc = boom
        env = lp._session_display_env()
        check('systemctl path returns DISPLAY', env.get('DISPLAY') == ':0', str(env))
        check('systemctl path returns WAYLAND_DISPLAY',
              env.get('WAYLAND_DISPLAY') == 'wayland-0')

        lp.subprocess.run = lambda *a, **k: types.SimpleNamespace(
            stdout='XDG_RUNTIME_DIR=/run/user/1001\n')
        lp._env_from_proc = lambda: {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}
        env = lp._session_display_env()
        check('proc fallback when systemctl lacks display',
              env.get('WAYLAND_DISPLAY') == 'wayland-0', str(env))

        lp.shutil.which = lambda name: None
        lp._env_from_proc = lambda: {}
        check('empty when nothing found', lp._session_display_env() == {})

        # _mpv_env: existing DISPLAY means no probing
        os.environ.pop('WAYLAND_DISPLAY', None)
        os.environ['DISPLAY'] = ':0'
        lp._session_display_env = boom
        m = lp._mpv_env()
        check('mpv env keeps existing DISPLAY', m.get('DISPLAY') == ':0', str(m))

        # _mpv_env: missing display merges recovered env
        os.environ.pop('DISPLAY', None)
        lp._session_display_env = lambda: {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-0'}
        m = lp._mpv_env()
        check('mpv env merges recovered DISPLAY', m.get('DISPLAY') == ':0', str(m))
        check('mpv env merges recovered WAYLAND_DISPLAY',
              m.get('WAYLAND_DISPLAY') == 'wayland-0')
    finally:
        lp.subprocess.run = orig_run
        lp.shutil.which = orig_which
        lp._env_from_proc = orig_proc
        lp._session_display_env = orig_session
        if saved_display is None:
            os.environ.pop('DISPLAY', None)
        else:
            os.environ['DISPLAY'] = saved_display
        if saved_wl is None:
            os.environ.pop('WAYLAND_DISPLAY', None)
        else:
            os.environ['WAYLAND_DISPLAY'] = saved_wl

    print()
    print('TOTAL: %d passed, %d failed' % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())