#!/usr/bin/env python3
"""Find which m3u file the 11 box is using by matching channel names."""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name

# 11 box's channels
api = KodiAPI('192.168.100.11', 9090, protocol='tcp')
chs = get_all_channels(api)
ch_labels = [c.get('label', '') for c in chs]
print(f'11 box: {len(chs)} channels')
print(f'  first 10: {ch_labels[:10]}')
print(f'  湖南卫视: {find_channel_by_name(chs, "湖南卫视")}')

# Get the IPTV m3u
dir_ = r'E:\iptv'
for fn in sorted(os.listdir(dir_)):
    if not (fn.endswith('.m3u') or fn.endswith('.m3u8')):
        continue
    full = os.path.join(dir_, fn)
    with open(full, 'rb') as f:
        text = f.read().decode('utf-8', errors='replace')
    m3u_names = re.findall(r'tvg-name="([^"]*)"', text)
    overlap = set(m3u_names) & set(ch_labels)
    print(f'\n{fn}: {len(m3u_names)} entries, {len(overlap)} match 11 box')
    if len(overlap) >= 5:
        # Show the diff
        only_11 = sorted(set(ch_labels) - set(m3u_names))[:10]
        only_m3u = sorted(set(m3u_names) - set(ch_labels))[:10]
        print(f'  only in 11 box: {only_11}')
        print(f'  only in m3u:   {only_m3u}')
