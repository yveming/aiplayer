#!/usr/bin/env python3
"""Diagnostic: dump raw PVR.GetBroadcasts response for a channel."""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name

HOST = '192.168.100.11'
PORT = 9090

api = KodiAPI(host=HOST, port=PORT, protocol='tcp')
v = api.get_version()
print(f"version: {v}")
if not v or 'result' not in v:
    sys.exit(1)

channels = get_all_channels(api)
print(f"got {len(channels)} channels total")
target = find_channel_by_name(channels, '湖南卫视')
if not target:
    print("湖南卫视 not found in channel list")
    sys.exit(1)
cid = target['channelid']
print(f"湖南卫视 id={cid}, label={target.get('label')!r}")

# 1) Raw response with all properties
print("\n=== raw PVR.GetBroadcasts response ===")
resp = api.pvr_get_broadcasts(
    cid,
    ['title', 'starttime', 'endtime'],
    limits={'start': 0, 'end': 5},
)
print(json.dumps(resp, indent=2, ensure_ascii=False)[:5000])
