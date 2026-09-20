#!/usr/bin/env python3
"""Real-KODI end-to-end smoke test. Connects to the user's KODI server
and verifies that:

  1) Files.GetSources returns movie / music / video sources
  2) PVR.GetChannels returns at least 1 channel
  3) PVR.GetBroadcasts works on a known channel
  4) JSONRPC.Version reports a sane version

Doesn't play anything. Safe to run on a live KODI.

Usage:
    # Connection presets (override any field with --host/--port/...)
    python tests/test_e2e_real_kodi.py --box tcp
    python tests/test_e2e_real_kodi.py --box http
    # Explicit connection
    python tests/test_e2e_real_kodi.py --host 1.2.3.4 --port 9090
    # Find the catchup channel id and broadcast structure
    python tests/test_e2e_real_kodi.py --probe-channel "CCTV-1"
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.stdout.reconfigure(encoding='utf-8')

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name


def check(label, ok, detail=''):
    tag = 'PASS' if ok else 'FAIL'
    print(f'  [{tag}]  {label}  {detail}')
    return 0 if ok else 1


BOX_PRESETS = {
    # Transport-based presets with example defaults; override with CLI flags.
    'tcp': dict(host='kodi.local', port=9090, protocol='tcp',
                username='', password=''),
    'http': dict(host='kodi.local', port=8080, protocol='http',
                 username='kodi', password=''),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--box', choices=list(BOX_PRESETS), default=None,
                    help='Connection preset (tcp / http)')
    ap.add_argument('--host', default=None)
    ap.add_argument('--port', type=int, default=None)
    ap.add_argument('--protocol', choices=['tcp', 'http'], default=None)
    ap.add_argument('--username', default=None)
    ap.add_argument('--password', default=None)
    ap.add_argument('--probe-channel', default='CCTV-1综合',
                    help='Channel name to look up for the broadcast check')
    args = ap.parse_args()

    if args.box:
        preset = BOX_PRESETS[args.box]
        args.host = args.host if args.host is not None else preset['host']
        args.port = args.port if args.port is not None else preset['port']
        args.protocol = args.protocol if args.protocol is not None else preset['protocol']
        args.username = args.username if args.username is not None else preset['username']
        args.password = args.password if args.password is not None else preset['password']
    if args.host is None:
        args.host = 'kodi.local'
    if args.port is None:
        args.port = 9090
    if args.protocol is None:
        args.protocol = 'tcp'
    args.username = args.username or ''
    args.password = args.password or ''

    api = KodiAPI(host=args.host, port=args.port, protocol=args.protocol,
                  username=args.username, password=args.password)
    failures = 0

    print(f'KODI E2E smoke - {args.host}:{args.port} ({args.protocol}'
          f'{", auth" if args.username else ""})')
    print('=' * 60)

    # 1) Version
    print('\n[1] JSONRPC.Version')
    v = api.get_version()
    if v and 'result' in v:
        ver = v['result'].get('version', {})
        failures += check('version', True, f'major={ver.get("major")} minor={ver.get("minor")}')
    else:
        failures += check('JSONRPC.Version', False, f'response={v}')

    # 2) Files.GetSources - we need at least one source per type that
    # the skill actually uses (music + video for sure).
    print('\n[2] Files.GetSources')
    for media in ('music', 'video', 'movie'):
        r = api.files_get_sources(media)
        sources = r.get('result', {}).get('sources', []) if r else []
        # For movie, KODI returns 0 (the param is invalid); only assert
        # on the actually-supported media types.
        if media == 'movie':
            failures += check(f'GetSources({media!r}) responds',
                              r is not None, f'(movie has no enum; 0 sources is expected)')
        else:
            ok = bool(sources)
            detail = f'{len(sources)} source(s): ' + ', '.join(
                s.get('file', '?') for s in sources[:3])
            failures += check(f'GetSources({media!r}) has >=1 source', ok, detail)

    # 3) PVR channel list - we need at least 1 channel for live TV.
    print('\n[3] PVR channels')
    channels = get_all_channels(api)
    failures += check(f'>=1 PVR channel', len(channels) >= 1,
                      f'({len(channels)} total)')

    # 4) PVR broadcasts for the probed channel
    print(f'\n[4] PVR broadcasts ({args.probe_channel})')
    target_ch = find_channel_by_name(channels, args.probe_channel)
    if not target_ch:
        failures += check(f'find_channel({args.probe_channel!r})', False)
    else:
        cid = target_ch['channelid']
        r = api.pvr_get_broadcasts(cid, ['title', 'starttime', 'endtime'])
        if not r:
            failures += check(f'PVR.GetBroadcasts({cid})', False, 'no response')
        elif 'error' in r:
            failures += check(f'PVR.GetBroadcasts({cid})', False, f'error={r["error"]}')
        else:
            bs = r['result'].get('broadcasts', [])
            failures += check(f'PVR.GetBroadcasts({cid}) returns broadcasts',
                              len(bs) > 0, f'({len(bs)} returned)')
            if bs:
                sample = bs[0]
                ok = all(k in sample for k in ('title', 'starttime', 'endtime', 'broadcastid'))
                failures += check('first broadcast has title+starttime+endtime+broadcastid',
                                  ok, f"first={sample.get('title')!r}  id={sample.get('broadcastid')}")

    print('\n' + '=' * 60)
    if failures == 0:
        print('E2E: all checks passed')
        sys.exit(0)
    else:
        print(f'E2E: {failures} check(s) failed')
        sys.exit(1)


if __name__ == '__main__':
    main()
