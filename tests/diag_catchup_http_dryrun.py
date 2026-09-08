#!/usr/bin/env python3
"""Dry-run: build catchup URL via HTTP m3u + EPG (no KODI play).
Used to validate the self-contained path before bothering KODI.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from aiplayer.m3u_catchup import (parse_m3u, find_channel as m3u_find_channel,
                         build_catchup_url, get_x_tvg_url, parse_xmltv,
                         find_program_in_xmltv, _read_text)

LOCAL = timezone(timedelta(hours=8))
M3U = 'http://192.168.100.2:8000/iptv/iptv-10.m3u'

# Read m3u
m3u_text = _read_text(M3U)
epg_url = get_x_tvg_url(m3u_text)
print(f'x-tvg-url: {epg_url}')

entries = parse_m3u(m3u_text)
print(f'm3u channels: {len(entries)}')

# Find 湖南卫视
ch = m3u_find_channel(entries, '湖南卫视')
print(f'\n湖南卫视 in m3u: {ch is not None}')
if ch:
    print(f'  label     = {ch.get("label")}')
    print(f'  tvg-id    = {ch.get("tvg_id")}')
    print(f'  tvg-name  = {ch.get("tvg_name")}')
    print(f'  catchup-source = {ch.get("catchup_source")[:120] if ch.get("catchup_source") else None}')
    print(f'  catchup-days   = {ch.get("catchup_days")}')

# Parse EPG
print(f'\nFetching EPG from {epg_url}...')
epg_channels, programs = parse_xmltv(epg_url)
print(f'EPG: {len(epg_channels)} channels, {len(programs)} programs')

# Find 湖南卫视
print(f'\n湖南卫视 in EPG channels? {("湖南卫视" in epg_channels)}')
print(f'  epg display name = {epg_channels.get("湖南卫视")}')

# Find programme: yesterday 21:00 local
target = (datetime.now(LOCAL) - timedelta(days=1)).replace(
    hour=21, minute=0, second=0, microsecond=0)
print(f'\nFind programme at {target} on 湖南卫视...')
prog = find_program_in_xmltv(programs, '湖南卫视', target)
if prog:
    local_s = prog['start_utc'].astimezone(LOCAL)
    local_e = prog['end_utc'].astimezone(LOCAL)
    print(f'  found: {local_s:%Y-%m-%d %H:%M} - {local_e:%H:%M}  {prog["title"]!r}')

    # Build URL
    url = build_catchup_url(ch['catchup_source'],
                            prog['start_utc'], prog['end_utc'],
                            local_tz=LOCAL,
                            catchup_id=ch.get('catchup_days'))
    print(f'\nCatchup URL:')
    print(f'  {url}')
else:
    print('  NOT FOUND')

# Also try CCTV-1
print(f'\n--- CCTV-1 ---')
ch2 = m3u_find_channel(entries, 'CCTV-1')
print(f'CCTV-1 in m3u: {ch2 is not None}')
print(f'  tvg-id = {ch2.get("tvg_id") if ch2 else None}')

# 1.5 hour ago, today, on CCTV-1
target2 = (datetime.now(LOCAL) - timedelta(hours=1)).replace(
    minute=0, second=0, microsecond=0)
print(f'Find programme at {target2} on CCTV-1 (tvg-id={ch2.get("tvg_id") if ch2 else "?"})...')
prog2 = find_program_in_xmltv(programs, 'CCTV-1', target2)
if prog2:
    local_s = prog2['start_utc'].astimezone(LOCAL)
    local_e = prog2['end_utc'].astimezone(LOCAL)
    print(f'  found: {local_s:%Y-%m-%d %H:%M} - {local_e:%H:%M}  {prog2["title"]!r}')
    url2 = build_catchup_url(ch2['catchup_source'],
                             prog2['start_utc'], prog2['end_utc'],
                             local_tz=LOCAL,
                             catchup_id=ch2.get('catchup_days'))
    print(f'  URL: {url2}')
else:
    print('  NOT FOUND')
