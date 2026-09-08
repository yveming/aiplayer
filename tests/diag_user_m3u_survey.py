#!/usr/bin/env python3
"""Survey the user's m3u files to see what catchup-source formats
are actually in use."""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PATHS = [
    r'E:\iptv\iptv-full.m3u',
    r'E:\iptv\iptv-cmcc.m3u',
]

for fn in PATHS:
    if not os.path.exists(fn):
        print(f'  --- {fn}')
        continue
    print(f'\n========== {fn} ==========')
    with open(fn, 'rb') as f:
        data = f.read()
    text = data.decode('utf-8', errors='replace')
    # Find all #EXTINF lines
    extinf_count = len(re.findall(r'#EXTINF:', text))
    print(f'  #EXTINF lines: {extinf_count}')
    # catchup-source patterns
    pats = re.findall(r'catchup-source="([^"]*)"', text)
    print(f'  catchup-source occurrences: {len(pats)}')
    c = Counter(pats)
    for p, n in c.most_common(10):
        print(f'    {n:4d}  {p[:140]}')
    # Find lines with two-format mix (one m3u has both - the user
    # mentioned this).
    has_strftime = sum(1 for p in pats if '${(b)' in p or '${(e)' in p)
    has_vlc = sum(1 for p in pats if '{utc:' in p or '{utcend:' in p)
    has_kodi_seconds = sum(1 for p in pats if '{start}' in p or '{utc}' in p)
    has_kodi_strftime = sum(1 for p in pats if '{utctime}' in p or '{localtime}' in p)
    print(f'  has_strftime (e.g. ${{(b)yyyyMMddHHmmss}}): {has_strftime}')
    print(f'  has_vlc (e.g. {{utc:YmdHMS}}): {has_vlc}')
    print(f'  has_kodi_seconds (e.g. {{start}}): {has_kodi_seconds}')
    print(f'  has_kodi_strftime (e.g. {{utctime}}): {has_kodi_strftime}')

    # Also dump a few sample lines (one of each catchup-source format)
    seen = set()
    for line in text.splitlines():
        if 'catchup-source=' in line:
            m = re.search(r'catchup-source="([^"]*)"', line)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                print(f'\n  sample EXTINF:')
                print(f'    {line[:200]}')
                if len(seen) > 5:
                    break
