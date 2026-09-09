#!/usr/bin/env python3
"""Probe PVR.GetClients and PVR.GetProperties with full property sets.
The PVR client (id=1) might expose its config via these.
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI

TARGETS = [
    ('11 box',  '192.168.100.11', 9090, 'tcp',  '',     ''),
    ('Sony TV', '192.168.100.43', 8080, 'http', 'kodi', 'hermes'),
]

# Probe PVR.GetProperties with every conceivable property name
PVR_PROPS = [
    'available', 'recording', 'timer', 'tv',
    'playingchannel', 'playingtvchannel', 'playingrecordings',
    'clients', 'channels', 'groups', 'recordings',
    'enabled', 'running', 'active', 'name', 'version',
    'host', 'port', 'user', 'password', 'url', 'm3u',
    'm3uurl', 'm3upath', 'epg', 'epgurl', 'catchup',
    'catchupdays', 'catchupenabled', 'catchupdefault',
    'minimumversion', 'version', 'backend', 'backendname',
    'backendversion', 'connection', 'discspace', 'timeshift',
    'timeshiftsupported', 'isrecording', 'lastwatched',
    'streamurl', 'channelurl',
]


def show(label, r, maxlen=400):
    if r is None:
        print(f'  {label}: None')
        return
    if 'error' in r:
        print(f'  {label}: ERR {r["error"].get("code")}')
        return
    s = json.dumps(r.get('result', ''), ensure_ascii=False)
    if len(s) > maxlen:
        s = s[:maxlen] + '...'
    print(f'  {label}: {s}')


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        # PVR.GetClients (no params, all fields)
        r = api.jsonrpc('PVR.GetClients', {})
        show('PVR.GetClients (no params)', r)

        # PVR.GetClients with properties
        for props in [
            ['name', 'version', 'enabled', 'priority'],
            ['name', 'version', 'enabled', 'priority', 'clientid'],
            ['name', 'version', 'enabled', 'priority', 'clientid',
             'host', 'port'],
            ['all'],
        ]:
            r = api.jsonrpc('PVR.GetClients', {'properties': props})
            show(f'PVR.GetClients(properties={props})', r)

        # PVR.GetProperties with one at a time
        for p in PVR_PROPS:
            r = api.jsonrpc('PVR.GetProperties', {'properties': [p]})
            show(f'PVR.GetProperties(properties=[{p!r}])', r)


if __name__ == '__main__':
    main()
