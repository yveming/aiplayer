#!/usr/bin/env python3
"""Try PVR.GetClients and PVR.GetBroadcastDetails for streamurl/catchup info."""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name, get_epg_for_channel

TARGETS = [
    ('11 box',  '192.168.100.11', 9090, 'tcp',  '',     ''),
    ('Sony TV', '192.168.100.43', 8080, 'http', 'kodi', 'hermes'),
]


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        # 1. PVR.GetClients
        r = api.jsonrpc('PVR.GetClients', {})
        print('  PVR.GetClients:')
        if r and 'result' in r:
            for c in r['result'].get('clients', []):
                print('    %s (id=%s)  priority=%s  enabled=%s' %
                      (c.get('name'), c.get('clientid'),
                       c.get('priority'), c.get('enabled')))
        else:
            print('    err:', r.get('error', {}) if r else r)

        # 2. PVR.GetBroadcastDetails with a recent broadcast
        chs = get_all_channels(api)
        ch = find_channel_by_name(chs, '湖南卫视')
        if ch:
            epg = get_epg_for_channel(api, ch['channelid'])
            if epg:
                # Get the most recent broadcast
                from pvr_epg import parse_time
                epg.sort(key=lambda b: parse_time(b.get('endtime', '')) or
                         parse_time(b.get('starttime', '')) or __import__('datetime').datetime.min.replace(tzinfo=__import__('datetime').timezone.utc))
                b = epg[-1] if epg else None
                if b:
                    bid = b.get('broadcastid')
                    print(f'\n  most recent broadcast: {b.get("title")}  id={bid}')

                    for props in [
                        ['title', 'starttime', 'endtime'],
                        ['title', 'streamurl'],
                        ['title', 'url'],
                        ['title', 'hascatchup'],
                        ['title', 'epgeventid'],
                        ['title', 'channelid'],
                    ]:
                        r = api.jsonrpc('PVR.GetBroadcastDetails',
                                        {'broadcastid': bid,
                                         'properties': props})
                        if r and 'result' in r:
                            details = r['result'].get('broadcastdetails', {})
                            print(f'    with {props}:')
                            for k, v in details.items():
                                print(f'      {k}: {v}')
                        else:
                            err = r.get('error', {}) if r else {}
                            print(f'    with {props}: ERR {err.get("code")} {err.get("message", "")[:50]}')


if __name__ == '__main__':
    main()
