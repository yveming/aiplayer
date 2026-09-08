#!/usr/bin/env python3
"""End-to-end catchup test on 11 box using --m3u-url.
Tries 湖南卫视 yesterday 18:30 catchup, fetching the m3u from
the IPTV HTTP backend and building the URL ourselves.
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.m3u_catchup import parse_m3u, find_channel, build_catchup_url, \
    _read_text, discover_m3u
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name, \
    get_epg_for_channel, find_program_in_epg, parse_time
from datetime import timezone, timedelta


def main():
    api = KodiAPI('192.168.100.11', 9090, protocol='tcp')
    if not api.get_version():
        print('cannot connect to 11 box')
        return 1

    # 1. Find 湖南卫视
    chs = get_all_channels(api)
    ch = find_channel_by_name(chs, '湖南卫视')
    if not ch:
        print('湖南卫视 not found')
        return 1
    print(f'湖南卫视 id={ch["channelid"]}')

    # 2. Find yesterday 18:30 broadcast
    epg = get_epg_for_channel(api, ch['channelid'])
    prog = find_program_in_epg(epg, 'yesterday', '18:30')
    if not prog:
        print('no yesterday 18:30 program')
        return 1
    print(f'program: {prog.get("title")}  start={prog.get("starttime")}  '
          f'end={prog.get("endtime")}')

    # 3. Fetch m3u (auto-discover from IPTV backend)
    ch_names = [c.get('label', '') for c in chs]
    best_url, entries, overlap = discover_m3u(
        'http://192.168.100.2:8000/iptv/', ch_names)
    print(f'\nAuto-picked: {best_url}  overlap={overlap}/{len(ch_names)}')

    m3u_entry = find_channel(entries, '湖南卫视')
    if not m3u_entry:
        print('湖南卫视 not in m3u')
        return 1
    print(f'湖南卫视 in m3u:  catchup-source len={len(m3u_entry["catchup_source"])}')
    template = m3u_entry['catchup_source']
    print(f'template: {template[:200]}')

    # 4. Build URL
    start_utc = parse_time(prog.get('starttime', ''))
    end_utc = parse_time(prog.get('endtime', ''))
    if not (start_utc and end_utc):
        print('no valid broadcast times')
        return 1
    local_tz = timezone(timedelta(hours=8))
    url = build_catchup_url(template, start_utc, end_utc, local_tz=local_tz)
    print(f'\nBuilt URL: {url}')

    # 5. Show the result, but DON'T play (the user needs to confirm first)
    print('\nURL built successfully. Run pvr_epg.py to play it:')
    print(f'  python pvr_epg.py --host 192.168.100.11 --port 9090 \\')
    print(f'    --protocol tcp --action catchup --channel "湖南卫视" \\')
    print(f'    --date yesterday --time 18:30 --m3u-url http://192.168.100.2:8000/iptv/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
