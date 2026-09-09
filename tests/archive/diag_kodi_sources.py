#!/usr/bin/env python3
"""Dump the actual file paths KODI uses for its sources."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from aiplayer.kodi_api import KodiAPI

HOST = '192.168.100.11'
PORT = 9090
PWD = 'hermes'
USER = 'kodi'

api = KodiAPI(host=HOST, port=PORT, protocol='tcp', timeout=10)
ok = api.connect(username=USER, password=PWD)
print(f"connected: {ok}")
if not ok:
    sys.exit(1)

for media in ('music', 'movie', 'video'):
    print(f"\n=== sources for media='{media}' ===")
    resp = api.files_get_sources(media)
    if not resp or 'result' not in resp:
        print(f"  (no result: {resp})")
        continue
    for s in resp['result'].get('sources', []):
        print(f"  - label={s.get('label')!r}  file={s.get('file')!r}  share={s.get('share')!r}")
