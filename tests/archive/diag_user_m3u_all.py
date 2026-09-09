#!/usr/bin/env python3
"""Survey ALL m3u files at E:/iptv/ for catchup-source formats."""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

dir_ = r'E:\iptv'
for fn in sorted(os.listdir(dir_)):
    full = os.path.join(dir_, fn)
    if not (fn.endswith('.m3u') or fn.endswith('.m3u8')):
        continue
    with open(full, 'rb') as f:
        text = f.read().decode('utf-8', errors='replace')
    pats = re.findall(r'catchup-source="([^"]*)"', text)
    has_strftime = sum(1 for p in pats if '${(b)' in p or '${(e)' in p)
    has_vlc = sum(1 for p in pats if '{utc:' in p or '{utcend:' in p)
    has_kodi_seconds = sum(1 for p in pats if '{start}' in p or '{utc}' in p)
    has_kodi_strftime = sum(1 for p in pats if '{utctime}' in p or '{localtime}' in p)
    print(f'  {fn:40s}  lines={len(pats):4d}  '
          f'vlc={has_vlc:4d}  strftime={has_strftime:4d}  '
          f'sec={has_kodi_seconds:4d}  kstrf={has_kodi_strftime:4d}')

    # Dump unique catchup-source templates (max 5)
    c = Counter(pats)
    for p, n in c.most_common(3):
        print(f'      [{n:3d}] {p[:120]}')
