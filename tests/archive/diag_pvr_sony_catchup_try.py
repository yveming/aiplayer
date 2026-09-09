#!/usr/bin/env python3
"""Try playing a broadcast via broadcastid on the Sony TV.

The m3u's catchup-source template is parsed by the PVR client (PVR IPTV
Simple Client), not exposed via JSON-RPC. KODI's PVR client should
handle the catchup URL construction internally if we pass the
broadcastid correctly.
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from datetime import datetime, timedelta, timezone
from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name, get_epg_for_channel, find_program_in_epg

HOST = '192.168.100.43'
PORT = 8080
USER = 'kodi'
PWD = 'hermes'

api = KodiAPI(host=HOST, port=PORT, protocol='http', username=USER, password=PWD)
if not api.get_version():
    sys.exit(1)

channels = get_all_channels(api)
ch = find_channel_by_name(channels, '湖南卫视')
if not ch:
    print('no 湖南卫视')
    sys.exit(1)
cid = ch['channelid']
print(f"湖南卫视 id={cid}")

# Get broadcasts
epg = get_epg_for_channel(api, cid)
print(f"got {len(epg)} broadcasts")

# Find yesterday 18:30 (=湖南新闻联播)
from aiplayer.pvr_epg import parse_time
local_tz = timezone(timedelta(hours=8))
yesterday = (datetime.now(local_tz) - timedelta(days=1)).replace(
    hour=18, minute=30, second=0, microsecond=0)
yesterday_utc = yesterday.astimezone(timezone.utc)
print(f"target local: {yesterday}")
print(f"target UTC:   {yesterday_utc}")

for b in epg:
    st = parse_time(b.get('starttime', ''))
    et = parse_time(b.get('endtime', ''))
    if st and et and st <= yesterday_utc <= et:
        bid = b.get('broadcastid')
        print(f"\nFOUND: {b.get('title')!r}  id={bid}  {b.get('starttime')}-{b.get('endtime')}")
        # Try playing with broadcastid
        print("\n[try 1] Player.Open with broadcastid")
        item = {'broadcastid': bid}
        r = api.player_open_item(item)
        print(json.dumps(r, indent=2, ensure_ascii=False)[:500])
        if r and 'error' not in r:
            print("\n  -> succeeded! broadcastid works for catchup.")
            break
        # Try with recording-like approach
        print("\n[try 2] Player.Open with broadcastid + starttime/endtime + resume")
        item = {'broadcastid': bid, 'resume': True}
        r = api.player_open_item(item)
        print(json.dumps(r, indent=2, ensure_ascii=False)[:500])
        break
else:
    print("no broadcast found for yesterday 18:30")
