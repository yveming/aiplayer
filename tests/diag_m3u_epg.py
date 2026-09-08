#!/usr/bin/env python3
"""Fetch the EPG from x-tvg-url and inspect format.
Then try a small XMLTV parse to find 湖南卫视's broadcasts.
"""
import gzip
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

url = 'http://192.168.100.2:8000/iptv/iptv-epg.xml.gz'
print(f'Fetching {url}...')
r = urllib.request.urlopen(url, timeout=10)
raw = r.read()
print(f'  bytes: {len(raw)}')
# Try to decompress
try:
    text = gzip.decompress(raw).decode('utf-8', errors='replace')
    print(f'  decompressed: {len(text)} bytes')
except Exception as e:
    text = raw.decode('utf-8', errors='replace')
    print(f'  raw text: {len(text)} bytes  (gzip failed: {e})')

# Show first ~50 lines
lines = text.splitlines()
print(f'\nFirst 10 lines:')
for l in lines[:10]:
    print(f'  {l[:200]}')

# Parse
try:
    root = ET.fromstring(text)
except ET.ParseError as e:
    print(f'XML parse error: {e}')
    sys.exit(1)

# Count channels and programs
channels = root.findall('channel')
programs = root.findall('programme')
print(f'\nChannels: {len(channels)}')
print(f'Programs: {len(programs)}')

# Find 湖南卫视
hunan = [c for c in channels if '湖南卫视' in (c.get('id', '') + '' +
                                                (c.findtext('display-name') or ''))]
print(f'\n湖南卫视 channels:')
for c in hunan:
    name = c.findtext('display-name')
    print(f'  id={c.get("id")}  name={name}')

# Find its programs
for c in hunan:
    cid = c.get('id')
    progs = [p for p in programs if p.get('channel') == cid]
    print(f'\n湖南卫视 (channel={cid}) programs: {len(progs)}')
    for p in progs[:5]:
        title = p.findtext('title')
        print(f'  {p.get("start")} - {p.get("stop")}  {title}')

# Last 5 lines
print('\nLast 5 lines:')
for l in lines[-5:]:
    print(f'  {l[:200]}')
