#!/usr/bin/env python3
"""Dump all settings and look for pvr.iptvsimple entries."""
import json
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


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        r = api.jsonrpc('Settings.GetSettings', {})
        if not (r and 'result' in r):
            print('  no settings')
            continue
        settings = r['result'].get('settings', [])
        # Print all entries whose id contains 'iptv', 'pvr', or 'catchup'
        keep = [s for s in settings
                if any(k in s.get('id', '').lower()
                       for k in ('iptv', 'pvr.iptv', 'catchup', 'm3u'))]
        print(f'  total settings: {len(settings)}, kept: {len(keep)}')
        for s in keep:
            sid = s.get('id', '?')
            label = s.get('label', '?')
            val = s.get('value', '<no value>')
            if isinstance(val, str) and len(val) > 200:
                val = val[:200] + '...'
            print(f'    {sid}')
            print(f'      label: {label}')
            print(f'      value: {val}')


if __name__ == '__main__':
    main()
