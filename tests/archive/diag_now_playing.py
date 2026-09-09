#!/usr/bin/env python3
"""Show what's currently playing on KODI: title, file, time, position."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from aiplayer.kodi_api import KodiAPI

host = sys.argv[1] if len(sys.argv) > 1 else '192.168.100.11'
port = int(sys.argv[2]) if len(sys.argv) > 2 else 9090
proto = sys.argv[3] if len(sys.argv) > 3 else 'tcp'
api = KodiAPI(host, port, protocol=proto)

# Get active players
r = api.jsonrpc('Player.GetActivePlayers')
print('Player.GetActivePlayers:')
import json
print(json.dumps(r, indent=2, ensure_ascii=False))

result = r.get('result') or []
players = result if isinstance(result, list) else result.get('players', [])
if not players:
    print('  (no active players)')
    sys.exit(0)

pid = players[0].get('playerid')
print(f'\nPlayer.GetItem (playerid={pid}, props=[]):')
print(json.dumps(api.jsonrpc('Player.GetItem',
        {'playerid': pid, 'properties': []}),
        indent=2, ensure_ascii=False))

# Probe one property at a time
for props in (['title'], ['file'], ['time'], ['paused'], ['speed'],
              ['duration'], ['totaltime'], ['showtitle']):
    print(f'\n  props={props}:', end=' ')
    rr = api.jsonrpc('Player.GetItem', {'playerid': pid, 'properties': props})
    if 'error' in rr:
        print(f'ERR {rr["error"]["code"]}')
    else:
        item = (rr.get('result') or {}).get('item', {})
        print(json.dumps({p: item.get(p) for p in props if p in item},
                          ensure_ascii=False))
