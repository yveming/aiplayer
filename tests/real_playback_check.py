#!/usr/bin/env python3
"""Real-device playback checks (KODI + local mpv).

THIS PLAYS MEDIA: it tunes live TV, opens streams and mutates the playlist,
so run it deliberately (it is NOT part of tests/run_all.py). Every step is
followed by `stop` where it makes sense.

Usage:
    python tests/real_playback_check.py --box tcp --host <tcp-host>
    python tests/real_playback_check.py --box http --host <http-host>
    python tests/real_playback_check.py --box local
    python tests/real_playback_check.py --box tcp --skip tv,queue
    python tests/real_playback_check.py --box tcp --channel "CCTV-1"

Boxes:
    tcp    raw TCP JSON-RPC (port 9090); may reject PVR broadcastid catch-up
           (-32602), in which case `catchup` should fall back to m3u/XMLTV
    http   HTTP JSON-RPC (port 8080); PVR broadcastid catch-up works
    local  local mpv + config iptv.m3u streams
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.stdout.reconfigure(encoding='utf-8')

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, get_epg_for_channel, parse_time
from aiplayer.config import load_config
from aiplayer.m3u_catchup import parse_m3u, _read_text as m3u_read

LOCAL_TZ = timezone(timedelta(hours=8))

PASS = FAIL = SKIP = 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [PASS] {name}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name}  {detail}')


def skip(name, why=''):
    global SKIP
    SKIP += 1
    print(f'  [SKIP] {name}  {why}')


BOXES = {
    'tcp': dict(host='kodi.local', port=9090, protocol='tcp',
                username='', password=''),
    'http': dict(host='kodi.local', port=8080, protocol='http',
                 username='kodi', password=''),
    'local': None,
}


def conn_flags(box):
    b = BOXES[box]
    if b is None:
        return ['--local']
    flags = ['--host', b['host'], '--port', str(b['port']),
             '--protocol', b['protocol']]
    if b['username']:
        flags += ['--username', b['username'], '--password', b['password']]
    return flags


def cli(box, *args):
    cmd = [sys.executable, '-m', 'aiplayer.aiplayer'] + conn_flags(box) + list(args)
    env = {**os.environ, 'PYTHONPATH': SRC, 'PYTHONIOENCODING': 'utf-8'}
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env, timeout=90)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def kodi_api(box):
    b = BOXES[box]
    if b is None:
        return None
    return KodiAPI(b['host'], b['port'], b['username'], b['password'],
                   protocol=b['protocol'])


def m3u_entries():
    m3u = load_config().get('iptv', {}).get('m3u', '')
    if not m3u:
        return []
    try:
        return parse_m3u(m3u_read(m3u))
    except Exception as e:
        print(f'  (m3u unavailable: {e})')
        return []


def m3u_streams():
    """Return up to two stream URLs from the configured m3u."""
    return [e.get('stream_url') for e in m3u_entries() if e.get('stream_url')][:2]


def pick_channel(box, api):
    """Channel whose EPG covers (now - 1 day).

    Returns a query string that resolves both in KODI PVR and in the m3u
    (PVR labels like 'CCTV-1综合' often differ from m3u labels like 'CCTV-1',
    and the catch-up fallback searches the m3u by the query string).
    """
    m3u_labels = [e.get('label') or e.get('tvg_name') for e in m3u_entries()]
    m3u_labels = [l for l in m3u_labels if l]
    if api is None:
        return (m3u_labels[0] if m3u_labels else None), None

    target = datetime.now(timezone.utc) - timedelta(days=1)
    for ch in get_all_channels(api):
        pvr_label = ch.get('label') or ''
        query = pvr_label
        for ml in m3u_labels:
            if pvr_label and (ml in pvr_label or ml.lower() in pvr_label.lower()):
                query = ml
                break
        for b in get_epg_for_channel(api, ch['channelid']):
            st = parse_time(b.get('starttime', ''))
            et = parse_time(b.get('endtime', ''))
            if st and et and st <= target < et:
                return query, (st, et)
    return None, None


def step_tv(box, api, channel):
    print('\n[tv] live tune')
    if not channel:
        skip('tv live', 'no channel')
        return
    rc, out = cli(box, 'tv', channel)
    check('tv returns 0', rc == 0, out[-300:])
    check('tv did not report an error', 'Playback error' not in out, out[-300:])
    cli(box, 'stop')


def step_catchup(box, api, channel, window):
    print('\n[catchup] replay a past programme')
    if not channel or not window:
        skip('catchup', 'no channel/programme')
        return
    st, et = window
    local = st.astimezone(LOCAL_TZ)
    date_s = local.strftime('%Y-%m-%d')
    time_s = local.strftime('%H:%M')
    rc, out = cli(box, 'catchup', channel, '--date', date_s, '--time', time_s)
    check('catchup returns 0', rc == 0, out[-400:])
    check('catchup built or delegated a URL',
          ('Catchup URL:' in out) or ('Broadcast ID:' in out), out[-400:])
    if box == 'tcp':
        check('tcp box rejected broadcastid and fell back',
              'broadcastid failed' in out and
              'falling back to m3u/XMLTV catch-up patch' in out, out[-400:])
    cli(box, 'stop')


def kodi_media_files(api, n=2):
    """Up to `n` real media files the KODI box can play (from its sources).

    Live stream URLs are unsuitable for queue checks: KODI can place the same
    URL in both the audio and video playlists, which makes the active-playlist
    index ambiguous.
    """
    found = []
    for media in ('video', 'music'):
        r = api.files_get_sources(media)
        for s in (r or {}).get('result', {}).get('sources', []):
            path = s.get('file', '')
            if not path or path.startswith('addons'):
                continue
            d = api.files_get_directory(path, media='files')
            for it in (d or {}).get('result', {}).get('files', []):
                if it.get('filetype') == 'file' and it.get('file'):
                    found.append(it['file'])
                    if len(found) >= n:
                        return found
    return found


def _queue_count(box):
    rc, out = cli(box, 'list')
    return rc, [ln for ln in out.splitlines() if '. ' in ln], out


def _wait_queue(box, minimum, timeout=8):
    """Poll `list` until it shows at least `minimum` entries (KODI starts
    streams lazily, so the playlist may be empty for a moment after play)."""
    time.sleep(0.5)
    deadline = time.time() + timeout
    while True:
        rc, numbered, out = _queue_count(box)
        if rc == 0 and len(numbered) >= minimum:
            return numbered, out
        if time.time() >= deadline:
            return numbered, out
        time.sleep(0.5)


def step_queue(box):
    print('\n[queue] playfile / append / list / remove')
    api = kodi_api(box)
    if api is not None:
        # KODI: prefer real media files; live streams have ambiguous playlists.
        media = kodi_media_files(api, 2)
        if len(media) < 2:
            skip('queue', 'need 2 media files on the box')
            return
        u1, u2 = media
    else:
        urls = m3u_streams()
        if len(urls) < 2:
            skip('queue', 'need 2 m3u stream URLs')
            return
        u1, u2 = urls

    rc, out = cli(box, 'playfile', u1)
    check('playfile returns 0', rc == 0, out[-300:])
    numbered, out = _wait_queue(box, 1)
    check('playfile put an entry in the queue', len(numbered) >= 1, out[-300:])

    rc, out = cli(box, 'append', u2)
    check('append returns 0', rc == 0, out[-300:])
    check('append reports success', 'Appended:' in out, out[-300:])
    numbered, out = _wait_queue(box, 2)
    check('list shows both queued entries', len(numbered) >= 2, out[-300:])

    rc, out = cli(box, 'remove', u2)
    check('remove returns 0', rc == 0, out[-300:])
    check('remove reports success', 'Removed:' in out, out[-300:])

    cli(box, 'stop')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--box', choices=list(BOXES), default='tcp')
    ap.add_argument('--channel', default='', help='Override the auto-picked channel')
    ap.add_argument('--skip', default='', help='Comma list of steps: tv,catchup,queue')
    ap.add_argument('--host', default=None, help='Override the preset host')
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--protocol', choices=['tcp', 'http'], default=None)
    ap.add_argument('--username', default=None)
    ap.add_argument('--password', default=None)
    args = ap.parse_args()
    skip_steps = {s.strip() for s in args.skip.split(',') if s.strip()}

    if args.box != 'local':
        b = dict(BOXES[args.box])
        if args.host is not None:
            b['host'] = args.host
        if args.port is not None:
            b['port'] = args.port
        if args.protocol is not None:
            b['protocol'] = args.protocol
        if args.username is not None:
            b['username'] = args.username
        if args.password is not None:
            b['password'] = args.password
        BOXES[args.box] = b

    print(f'Real-device playback check: {args.box}')
    print('=' * 60)

    api = kodi_api(args.box)
    channel, window = (args.channel, None)
    if args.channel:
        if api is not None:
            target = datetime.now(timezone.utc) - timedelta(days=1)
            for ch in get_all_channels(api):
                if ch.get('label') == args.channel:
                    for b in get_epg_for_channel(api, ch['channelid']):
                        st = parse_time(b.get('starttime', ''))
                        et = parse_time(b.get('endtime', ''))
                        if st and et and st <= target < et:
                            channel, window = args.channel, (st, et)
                            break
                    break
    else:
        channel, window = pick_channel(args.box, api)

    if 'tv' not in skip_steps:
        step_tv(args.box, api, channel)
    if 'catchup' not in skip_steps:
        step_catchup(args.box, api, channel, window)
    if 'queue' not in skip_steps:
        step_queue(args.box)

    print('\n' + '=' * 60)
    print(f'{args.box}: {PASS} passed, {FAIL} failed, {SKIP} skipped')
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == '__main__':
    main()
