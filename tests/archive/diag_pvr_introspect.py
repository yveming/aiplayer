#!/usr/bin/env python3
"""Probe additional JSON-RPC namespaces for IPTV/PVR info."""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI

TARGETS = [
    ('11 box',  '192.168.100.11', 9090, 'tcp',  '',     ''),
    ('Sony TV', '192.168.100.43', 8080, 'http', 'kodi', 'hermes'),
]

# Namespaces worth probing for catch-up/stream URL info.
PROBES = [
    # Standard
    ('JSONRPC.Version',           {}),
    ('JSONRPC.Introspect',        {'getdescriptions': False}),
    ('JSONRPC.Permission',        {}),
    # PVR
    ('PVR.GetProviders',          {}),
    ('PVR.GetProperties',         {'properties': ['available', 'recording']}),
    # Player
    ('Player.GetActivePlayers',   {}),
    # System
    ('System.GetInfoLabels',      {'labels': ['Network.IPAddress',
                                              'System.FriendlyName',
                                              'System.BuildVersion']}),
    # XBMC
    ('XBMC.GetInfoLabels',        {'labels': ['System.BuildVersion']}),
]


def show(resp, label, maxlen=200):
    if resp is None:
        print(f'  {label}: None')
        return
    if 'error' in resp:
        print(f'  {label}: ERR {resp["error"].get("code")}')
        return
    s = str(resp.get('result', ''))[:maxlen]
    print(f'  {label}: {s}')


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        for method, params in PROBES:
            try:
                r = api.jsonrpc(method, params)
            except Exception as e:
                print(f'  {method}: EXC {e}')
                continue
            if method == 'JSONRPC.Introspect':
                # show the methods list
                if r and 'result' in r:
                    methods = r['result'].get('methods', [])
                    # Filter to interesting ones
                    keep = [m for m in methods
                            if any(k in m for k in ('PVR.', 'Files.',
                                                    'Settings.', 'Addons.',
                                                    'XBMC.', 'System.',
                                                    'Player.', 'JSONRPC.'))]
                    print(f'  JSONRPC.Introspect: {len(methods)} total, {len(keep)} interesting')
                    for m in sorted(keep)[:80]:
                        print(f'    {m}')
                else:
                    show(r, method)
            else:
                show(r, method)


if __name__ == '__main__':
    main()
