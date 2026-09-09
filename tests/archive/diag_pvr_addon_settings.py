#!/usr/bin/env python3
"""Probe KODI for the PVR IPTV Simple Client's configuration.
The user says there's no m3u file - the m3u is fetched from a URL and
parsed in memory by the PVR client.  We need to find:
  1. The m3u URL (so we can re-fetch and re-parse it ourselves)
  2. OR the per-channel streamurl / catchup-source directly

KODI API surface to probe:
  - Settings.GetSettings with filter=pvr.iptvsimple
  - Settings.GetSettingValue for each known key
  - Addons.GetAddonDetails for pvr.iptvsimple
  - Addons.ExecuteAddon (probably won't work over JSON-RPC)
"""
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

# Known IPTV Simple Client setting keys
SETTING_KEYS = [
    'pvrmanager.enabled',
    'pvr.iptvsimple.enabled',
    'pvr.iptvsimple.m3uurl',
    'pvr.iptvsimple.m3uUrl',
    'pvr.iptvsimple.m3u_path',
    'pvr.iptvsimple.epgurl',
    'pvr.iptvsimple.epgUrl',
    'pvr.iptvsimple.catchupenabled',
    'pvr.iptvsimple.catchupwindow',
    'pvr.iptvsimple.catchupqueryparameter',
    'pvr.iptvsimple.catchupdefaultquery',
    'pvr.iptvsimple.catchupcachemode',
    'pvr.iptvsimple.catchupdays',
    'pvr.iptvsimple.catchupcorrection',
    'pvr.iptvsimple.catchupurlsyntax',
]


def show(resp, label):
    if resp is None:
        print(f'  {label}: <no response>')
        return
    if 'error' in resp:
        print(f'  {label}: ERR {resp["error"].get("code")} {resp["error"].get("message")}')
        return
    out = resp.get('result', {})
    if isinstance(out, dict):
        if 'value' in out:
            print(f'  {label}: {out["value"]!r}')
        else:
            s = json.dumps(out, ensure_ascii=False)
            print(f'  {label}: {s[:300]}')
    else:
        print(f'  {label}: {out}')


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        # 1. Settings.GetSettings filtered to pvr.iptvsimple
        try:
            r = api.jsonrpc('Settings.GetSettings',
                            {'filter': {'section': 'pvr.iptvsimple'}})
            show(r, 'Settings.GetSettings(filter=pvr.iptvsimple)')
        except Exception as e:
            print(f'  Settings.GetSettings threw: {e}')

        # 2. Addons.GetAddonDetails
        try:
            r = api.jsonrpc('Addons.GetAddonDetails',
                            {'addonid': 'pvr.iptvsimple',
                             'properties': ['name', 'version', 'enabled',
                                            'summary', 'path', 'profile',
                                            'dependencies']})
            show(r, 'Addons.GetAddonDetails(pvr.iptvsimple)')
        except Exception as e:
            print(f'  Addons.GetAddonDetails threw: {e}')

        # 3. Settings.GetSettingValue for each known key
        print('\n  --- Settings.GetSettingValue ---')
        for k in SETTING_KEYS:
            r = api.jsonrpc('Settings.GetSettingValue', {'setting': k})
            show(r, k)


if __name__ == '__main__':
    main()
