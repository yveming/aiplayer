#!/usr/bin/env python3
"""Scan all PVR channels for catch-up support."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels

HOST = '192.168.100.11'
PORT = 9090
api = KodiAPI(host=HOST, port=PORT, protocol='tcp')
v = api.get_version()
if not v or 'result' not in v:
    sys.exit(1)

channels = get_all_channels(api)
print(f"got {len(channels)} channels, checking catchup flag...")
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

print(f"\n{len(have_catchup)} of {len(channels)} channels have catch-up support:")
for label, cid, url in have_catchup[:15]:
    print(f"  [{cid}] {label!r}  url={'set' if url else 'missing'}")
