#!/usr/bin/env python3
"""Try to read addon settings via KODI's HTTP /kodi-fs/ endpoint.
This is a different HTTP path from /jsonrpc and may bypass the
JSON-RPC namespace allowlist.
"""
import base64
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding='utf-8')

TARGETS = [
    ('11 box',  'http://192.168.100.11:8080', '',     ''),
    ('Sony TV', 'http://192.168.100.43:8080', 'kodi', 'hermes'),
]

# Common IPTV client addon storage locations on the box's filesystem.
# KODI converts special:// paths to filesystem paths on its host.
# The 11 box runs CoreELEC (Android-like) so /storage/.kodi/...
PATHS = [
    '/storage/.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
    '/storage/.kodi/userdata/addon_data/pvr.iptvsimple/',
    '/.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
    '/kodi-fs/storage/.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
    '/kodi-fs/.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
    # Image proxy might also be available at /vfs/ or similar
    '/vfs/storage/.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
]


def try_url(url, user, pwd, path):
    """Try a KODI HTTP endpoint."""
    full = f'{url}{path}'
    req = urllib.request.Request(full)
    if user:
        cred = base64.b64encode(f'{user}:{pwd}'.encode()).decode()
        req.add_header('Authorization', f'Basic {cred}')
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()[:2000].decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500].decode('utf-8', errors='replace')
    except Exception as e:
        return None, str(e)[:200]


def main():
    for name, base, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        for p in PATHS:
            code, body = try_url(base, user, pwd, p)
            tag = 'OK ' if code == 200 else (str(code) if code else 'ERR')
            print(f'  [{tag}] {p}')
            if code == 200:
                # Show first 500 chars
                print(f'    {body[:500]}')
            elif body:
                print(f'    {body[:200]}')


if __name__ == '__main__':
    main()
