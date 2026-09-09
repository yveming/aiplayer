#!/usr/bin/env python3
"""Dump raw PVR.GetChannelDetails for one Sony TV channel to see what
catch-up related fields are exposed (or not)."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name

HOST = '192.168.100.43'
PORT = 8080
USER = 'kodi'
PWD = 'hermes'

api = KodiAPI(host=HOST, port=PORT, protocol='http', username=USER, password=PWD)
v = api.get_version()
if not v or 'result' not in v:
    sys.exit(1)

channels = get_all_channels(api)
for q in ['湖南卫视', 'CCTV-1', 'CCTV-5']:
    ch = find_channel_by_name(channels, q)
    if not ch:
        print(f'{q!r}: not found')
        continue
    cid = ch['channelid']
    print(f'\n=== {q!r}  (id={cid}) ===')
    # Try with no properties (default)
    r1 = api.pvr_get_channel_details(cid)
    print('default:')
    print(json.dumps(r1, indent=2, ensure_ascii=False)[:2000])
    # Try with explicit catchup properties
    r2 = api.pvr_get_channel_details(
        cid,
        properties=['hascatchup', 'catchupid', 'streamurl', 'url', 'properties',
                    'icon', 'name', 'number', 'inputstreamclass'],
    )
    print('\nwith catchup properties:')
    print(json.dumps(r2, indent=2, ensure_ascii=False)[:2000])
