#!/usr/bin/env python3
"""Examine the 46-channel m3u files in detail."""
import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

FILES = [
    r'E:\iptv\iptv精选.m3u',
    r'E:\iptv\iptv精选-10.m3u',
    r'E:\iptv\iptv精选-cdtv.m3u',
]

for fn in FILES:
    if not os.path.exists(fn):
        print(f'--- {fn}')
        continue
    print(f'\n========== {fn} ==========')
    with open(fn, 'rb') as f:
        text = f.read().decode('utf-8', errors='replace')
    lines = text.splitlines()
    print(f'  total lines: {len(lines)}')
    extinf_idx = [i for i, l in enumerate(lines) if l.startswith('#EXTINF:')]
    print(f'  #EXTINF: {len(extinf_idx)}')

    # Show first 3 #EXTINF + URL lines
    print(f'  first 3 entries:')
    for i in extinf_idx[:3]:
        print(f'    {lines[i][:200]}')
        if i + 1 < len(lines):
            print(f'    {lines[i+1][:200]}')

    # Look for 湖南卫视
    for i in extinf_idx:
        if '湖南卫视' in lines[i]:
            print(f'  湖南卫视 at line {i}:')
            print(f'    {lines[i][:300]}')
            if i + 1 < len(lines):
                print(f'    {lines[i+1][:200]}')
            break

    # Unique catchup-source templates
    pats = re.findall(r'catchup-source="([^"]*)"', text)
    print(f'  unique catchup templates: {len(set(pats))}')
    from collections import Counter
    c = Counter(pats)
    for p, n in c.most_common(5):
        print(f'    [{n}] {p[:140]}')
