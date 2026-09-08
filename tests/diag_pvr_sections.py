#!/usr/bin/env python3
"""Try every variant of Settings.GetSettings to find the IPTV config."""
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

FILTERS = [
    {},
    {'level': 'expert'},
    {'level': 'standard'},
    {'level': 'basic'},
    {'filter': {'section': 'pvr'}},
    {'filter': {'section': 'pvr.iptvsimple'}},
    {'filter': {'category': 'pvr'}},
    {'filter': {'category': 'pvr.iptvsimple'}},
    {'filter': {'section': 'addons'}},
    {'filter': {'section': 'services'}},
]


def show(resp, maxlen=200):
    if not resp:
        return 'None'
    if 'error' in resp:
        return 'ERR %s %s' % (resp['error'].get('code'),
                              resp['error'].get('message', '')[:maxlen])
    s = str(resp.get('result', ''))[:maxlen]
    return s


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        for f in FILTERS:
            r = api.jsonrpc('Settings.GetSettings', f)
            print(f'  Settings.GetSettings({f}):')
            line = show(r)
            print(f'    {line}')

        # Also try listing categories
        r = api.jsonrpc('Settings.GetCategories', {})
        print(f'  Settings.GetCategories:')
        if r and 'result' in r:
            for c in r['result'].get('categories', []):
                print(f'    {c.get("label")} (id={c.get("categoryid")})')
        else:
            print(f'    {show(r)}')

        # Sections
        r = api.jsonrpc('Settings.GetSections', {})
        print(f'  Settings.GetSections:')
        if r and 'result' in r:
            secs = [s for s in r['result'].get('sections', [])
                    if 'pvr' in str(s.get('id', '')).lower() or
                       'iptv' in str(s.get('id', '')).lower() or
                       'addons' in str(s.get('id', '')).lower()]
            for s in secs[:30]:
                print(f'    {s.get("id")}  {s.get("label")}')
        else:
            print(f'    {show(r)}')


if __name__ == '__main__':
    main()
