#!/usr/bin/env python3
"""Try every conceivable Player.Open form for catchup on the 11 box.
The 11 box PVR client returns -32602 on broadcastid.  We try:
  - Player.Open({channelid, position: -X})  -- seek into timeshift buffer
  - Player.Open({channelid, position: 0})    -- always live
  - Player.Open({broadcastid, ...})          -- various property combos
  - Player.Open({recordingid})              -- not applicable
The position param is in SECONDS relative to live (negative = past).
The 11 box might support seek-back if its PVR backend has timeshift.
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name, get_epg_for_channel, find_program_in_epg, parse_time

api = KodiAPI(host='192.168.100.11', port=9090, protocol='tcp')
if not api.get_version():
    print('cannot connect to 11 box')
    sys.exit(1)

# 1. Find a recent past broadcast for 湖南卫视
chs = get_all_channels(api)
ch = find_channel_by_name(chs, '湖南卫视')
print(f'湖南卫视 id={ch["channelid"]}')

epg = get_epg_for_channel(api, ch['channelid'])
prog = find_program_in_epg(epg, 'yesterday', '18:30')
if not prog:
    print('no yesterday 18:30 broadcast - using most recent ended')
    # Use the most recently ended broadcast
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    ended = [b for b in epg if parse_time(b.get('endtime', '')) and
             parse_time(b.get('endtime', '')) < now]
    if ended:
        prog = sorted(ended, key=lambda b: parse_time(b.get('endtime', '')))[-1]
print(f'program: {prog.get("title")}  start={prog.get("starttime")}  end={prog.get("endtime")}')

st = parse_time(prog.get('starttime', ''))
et = parse_time(prog.get('endtime', ''))
now_utc = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
position_sec = int((now_utc - st).total_seconds()) if st else None
print(f'seconds from broadcast start to now: {position_sec}')

# 2. Stop any current playback
api.player_stop()
import time; time.sleep(1)

# 3. Try various forms
attempts = []

# 3a. broadcastid (we know it fails - just to confirm)
attempts.append((
    'broadcastid only',
    {'broadcastid': prog.get('broadcastid')}
))

# 3b. broadcastid + position
if position_sec is not None:
    attempts.append((
        'broadcastid + position 0',
        {'broadcastid': prog.get('broadcastid'), 'position': 0}
    ))
    attempts.append((
        'broadcastid + position seek',
        {'broadcastid': prog.get('broadcastid'), 'position': position_sec}
    ))

# 3c. channelid + position (negative for timeshift)
attempts.append((
    'channelid + position 0 (live)',
    {'channelid': ch['channelid'], 'position': 0}
))
if position_sec is not None:
    attempts.append((
        f'channelid + position -3600 (1h back)',
        {'channelid': ch['channelid'], 'position': -3600}
    ))
    attempts.append((
        f'channelid + position {position_sec} (back to prog start)',
        {'channelid': ch['channelid'], 'position': position_sec}
    ))

# 3d. Just file (empty / dummy - to see error format)
# attempts.append(('file: invalid', {'file': 'http://invalid'}))

# 3e. recordingid
# recordingid is for completed recordings, not catchup

for label, item in attempts:
    print(f'\n>>> {label}')
    print(f'    item = {json.dumps(item)}')
    r = api.jsonrpc('Player.Open', {'item': item})
    if r and 'result' in r:
        print(f'    OK: {r["result"]}')
    else:
        err = r.get('error', {}) if r else {}
        print(f'    ERR: {err.get("code")} {err.get("message", "")[:80]}')

print('\nDone.')
