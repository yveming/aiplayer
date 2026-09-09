#!/usr/bin/env python3
"""Files.GetDirectory with proper media type filter.
Earlier the right call uses media='video' for movie/video and
media='files' for raw filesystem.  Also try without media param.
"""
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

# The user has /Public/ on NFS at 192.168.100.2, mount paths we KNOW work
KNOWN_DIRS = [
    ('nfs://192.168.100.2/Public/',       'files'),
    ('nfs://192.168.100.2/Public/',       'video'),
    ('nfs://192.168.100.2/Public/movie/', 'video'),
    ('nfs://192.168.100.2/Public/music/', 'music'),
    ('nfs://192.168.100.2/Public/video/', 'video'),
]

# Try addon locations as Files with media=files (raw filesystem)
# These need to be reachable from KODI's filesystem namespace, not special://
ADDON_PATHS = [
    '/storage/.kodi/userdata/addon_data/pvr.iptvsimple/',          # LibreELEC
    '/storage/.kodi/userdata/',
    '/.kodi/userdata/',
    '/home/osmc/.kodi/userdata/',                                    # OSMC
    '/home/pi/.kodi/userdata/',                                      # Raspberry Pi
    '/config/addon_data/pvr.iptvsimple/',                            # Docker linuxserver
    '/var/lib/kodi/.kodi/userdata/addon_data/pvr.iptvsimple/',       # Linux
]


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        # Sanity: confirm /Public/ is reachable
        for p, m in KNOWN_DIRS:
            r = api.files_get_directory(p, media=m)
            if r and 'result' in r:
                files = r['result'].get('files', [])
                print(f'  {p}  media={m:5}  -> {len(files)} entries')
            else:
                err = r.get('error', {}) if r else {}
                print(f'  {p}  media={m:5}  -> ERR {err.get("code")} {err.get("message")}')

        # Try addon paths (raw fs)
        for p in ADDON_PATHS:
            r = api.files_get_directory(p, media='files')
            if r and 'result' in r:
                files = r['result'].get('files', [])
                print(f'  {p}  -> {len(files)} entries')
                for f in files[:10]:
                    print(f'    {f.get("filetype", "?"):8} {f.get("label", "?")}')
            else:
                err = r.get('error', {}) if r else {}
                print(f'  {p}  -> ERR {err.get("code")} {err.get("message", "")[:50]}')


if __name__ == '__main__':
    main()
