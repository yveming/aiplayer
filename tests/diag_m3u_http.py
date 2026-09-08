#!/usr/bin/env python3
"""Fetch the IPTV m3u from the user's HTTP backend and inspect formats.
URL: http://192.168.100.2:8000/iptv/iptv-10.m3u  (used by 11 box)
URL: http://192.168.100.2:8000/iptv/iptv-full.m3u (probably used by Sony TV)
"""
import urllib.request
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

URLS = [
    'http://192.168.100.2:8000/iptv/iptv-10.m3u',
    'http://192.168.100.2:8000/iptv/iptv-full.m3u',
    'http://192.168.100.2:8000/iptv/iptv-cmcc.m3u',
    'http://192.168.100.2:8000/',
]

for url in URLS:
    print(f'\n========== {url} ==========')
    try:
        r = urllib.request.urlopen(url, timeout=5)
        text = r.read().decode('utf-8', errors='replace')
        lines = text.splitlines()
        n_extinf = sum(1 for l in lines if l.startswith('#EXTINF:'))
        pats = re.findall(r'catchup-source="([^"]*)"', text)
        has_vlc = sum(1 for p in pats if '{utc:' in p or '{utcend:' in p)
        has_strftime = sum(1 for p in pats if '${(b)' in p or '${(e)' in p)
        print(f'  status={r.status}  bytes={len(text)}  extinf={n_extinf}  catchup={len(pats)}')
        print(f'  vlc={has_vlc}  strftime={has_strftime}')

        # Look for 湖南卫视
        for i, line in enumerate(lines):
            if '湖南卫视' in line:
                print(f'  湖南卫视 at line {i}:')
                print(f'    {line[:300]}')
                if i + 1 < len(lines):
                    print(f'    {lines[i+1][:200]}')
                break
    except Exception as e:
        print(f'  ERR: {e}')
