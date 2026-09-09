#!/usr/bin/env python3
"""Test parse_xmltv + find_program_in_xmltv against the real EPG."""
import os
import sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from aiplayer.m3u_catchup import parse_xmltv, get_x_tvg_url, find_program_in_xmltv, _read_text

EPG_URL = 'http://192.168.100.2:8000/iptv/iptv-epg.xml.gz'
M3U_URL = 'http://192.168.100.2:8000/iptv/iptv-10.m3u'
LOCAL = timezone(timedelta(hours=8))

print('Fetching m3u to read x-tvg-url...')
m3u = _read_text(M3U_URL)
epg = get_x_tvg_url(m3u)
print(f'  x-tvg-url = {epg}')

print('\nFetching + parsing EPG...')
channels, programs = parse_xmltv(EPG_URL)
print(f'  channels: {len(channels)}  programs: {len(programs)}')
print(f'  sample channel: id={list(channels.keys())[0]}  name={list(channels.values())[0]}')

# Find 湖南卫视 programs
hunan = [p for p in programs if p['channel'] == '湖南卫视']
print(f'\n湖南卫视 programs: {len(hunan)}')
for p in hunan[:3]:
    local = p['start_utc'].astimezone(LOCAL)
    print(f"  {local:%Y-%m-%d %H:%M} → {p['title']}")

# Try finding a programme: yesterday 21:00 (local)
yesterday = (datetime.now(LOCAL) - timedelta(days=1)).replace(
    hour=21, minute=0, second=0, microsecond=0)
print(f"\nFind programme at {yesterday} on 湖南卫视...")
p = find_program_in_xmltv(programs, '湖南卫视', yesterday)
if p:
    local_s = p['start_utc'].astimezone(LOCAL)
    local_e = p['end_utc'].astimezone(LOCAL)
    print(f"  found: {local_s:%Y-%m-%d %H:%M} - {local_e:%H:%M}  '{p['title']}'")
else:
    print('  NOT FOUND')

# Look at all 湖南卫视 programs for that day
target_day = yesterday.date()
print(f'\n湖南卫视 programs on {target_day} (local):')
for p in programs:
    if p['channel'] != '湖南卫视':
        continue
    local = p['start_utc'].astimezone(LOCAL)
    if local.date() == target_day:
        print(f"  {local:%H:%M}  {p['title']}")
