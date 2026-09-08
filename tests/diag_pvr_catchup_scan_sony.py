#!/usr/bin/env python3
"""Scan the Sony TV (192.168.100.43:8080, HTTP) for catch-up support.
Same as diag_pvr_catchup_scan.py but with HTTP+auth defaults."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels

HOST = '192.168.100.43'
PORT = 8080
USER = 'kodi'
PWD = 'hermes'

api = KodiAPI(host=HOST, port=PORT, protocol='http', username=USER, password=PWD)
v = api.get_version()
print(f'version: {v}')
if not v or 'result' not in v:
    print('cannot connect')
    sys.exit(1)

channels = get_all_channels(api)
print(f'\ngot {len(channels)} channels')
for ch in channels[:30]:
    print(f"  [{ch.get('channelid')}] {ch.get('label')!r}  group={ch.get('group')!r}")

print('\n--- catchup scan ---')
have_catchup = []
for ch in channels:
    cid = ch['channelid']
    r = api.pvr_get_channel_details(
        cid,
        properties=['hascatchup', 'catchupid', 'streamurl', 'url'],
    )
    det = r.get('result', {}).get('channeldetails', {}) if r else {}
    if det.get('hascatchup'):
        have_catchup.append((det.get('label') or ch.get('label'), cid, det.get('streamurl') or det.get('url')))

print(f'{len(have_catchup)} of {len(channels)} channels have catch-up support:')
for label, cid, url in have_catchup[:15]:
    print(f'  [{cid}] {label!r}  url={"set" if url else "missing"}')
