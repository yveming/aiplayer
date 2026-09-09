#!/usr/bin/env python3
"""Inspect the EXTM3U header of the user's m3u to see x-tvg-url etc.
The EPG URL is right at the top of the m3u file.
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.m3u_catchup import _read_text

URLS = [
    'http://192.168.100.2:8000/iptv/iptv-10.m3u',
    'http://192.168.100.2:8000/iptv/iptv-full.m3u',
    'http://192.168.100.2:8000/iptv/iptv-cmcc.m3u',
]

for url in URLS:
    print(f'\n========== {url} ==========')
    try:
        text = _read_text(url)
    except Exception as e:
        print(f'  ERR: {e}')
        continue
    # First line is the EXTM3U header
    first = text.splitlines()[0] if text.splitlines() else ''
    print(f'  {first}')
    # Look for any URL-like attributes in the first few lines
    for line in text.splitlines()[:5]:
        if line.startswith('#'):
            print(f'  {line[:300]}')
