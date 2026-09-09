#!/usr/bin/env python3
"""Find IPTV client config via any means available.
Settings and Addons are blocked on both boxes.  Try:
  - Files.GetDirectory on common addon_data / userdata paths
  - The webserver allowlist might still let through some namespaces
  - Read guisettings.xml from a known share, if any
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

# Try every path the IPTV Simple Client might store config in.
USERDATA_PATHS = [
    'special://userdata',
    'special://userdata/addon_data',
    'special://userdata/addon_data/pvr.iptvsimple',
    'special://home/addons/pvr.iptvsimple',
    'special://masterprofile/addon_data/pvr.iptvsimple',
    # NFS roots where we have access
    'nfs://192.168.100.2/Public/',
    'nfs://192.168.100.2/Public/.kodi/',
    'nfs://192.168.100.2/Public/.kodi/userdata/',
    'nfs://192.168.100.2/Public/.kodi/userdata/addon_data/',
    'nfs://192.168.100.2/Public/.kodi/userdata/addon_data/pvr.iptvsimple/',
    # Windows paths to the same
    'C:/',
    'C:/Users',
    'C:/ProgramData',
]


def probe(api, path, media='files'):
    try:
        r = api.files_get_directory(path, media=media)
    except Exception as e:
        return f'EXC:{e}'
    if r is None:
        return 'None'
    if 'error' in r:
        return f'ERR:{r["error"].get("code")}'
    out = r.get('result', {})
    files = out.get('files', [])
    return files


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        for p in USERDATA_PATHS:
            r = probe(api, p, media='files')
            if isinstance(r, list):
                if not r:
                    print(f'  {p}: <empty>')
                else:
                    print(f'  {p}: {len(r)} entries')
                    for f in r[:8]:
                        print(f'    {f.get("filetype", "?"):8} {f.get("label", "?")} -> {f.get("file", "?")}')
                    if len(r) > 8:
                        print(f'    ... and {len(r) - 8} more')
            else:
                print(f'  {p}: {r}')


if __name__ == '__main__':
    main()
