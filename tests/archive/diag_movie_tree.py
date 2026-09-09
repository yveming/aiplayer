#!/usr/bin/env python3
"""Quick diagnostic: dump full tree of /Public/movie/ (depth 2)."""
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

def walk(path, depth=0, max_depth=2):
    indent = '  ' * depth
    print(f"{indent}[dir] {path}")
    if depth > max_depth:
        return
    resp = api.files_get_directory(path)
    if not resp or 'result' not in resp:
        print(f"{indent}  (no result)")
        return
    files = resp['result'].get('files', [])
    for f in files:
        ftype = f.get('filetype', '?')
        label = f.get('label', '?')
        fpath = f.get('file', '?')
        print(f"{indent}  [{ftype}] {label!r}  -> {fpath}")
        if ftype == 'directory':
            walk(fpath, depth + 1, max_depth)

walk('nfs://192.168.100.2/Public/movie/', 0, 2)
