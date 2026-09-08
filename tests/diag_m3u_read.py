#!/usr/bin/env python3
"""Find and read the PVR IPTV Simple Client m3u file on a KODI box,
and dump the catchup-source templates for a few channels.

Strategy:
  1) Look in KODI's addon_data for pvr.iptvsimple/settings.xml
     (~/.kodi/userdata/addon_data/pvr.iptvsimple/ on Linux,
     C:/Users/<u>/AppData/Roaming/Kodi/userdata/... on Windows).
  2) Read the m3u path / URL from that file.
  3) If it's a local path under KODI's filesystem, read it via
     Files.GetDirectory (KODI can list any directory it has access to).
  4) Parse the m3u and dump the catchup-source line for a sample of
     channels so we can see which placeholder syntax is used.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI

# Both boxes the user has
TARGETS = [
    ('11 box',   '192.168.100.11', 9090, 'tcp',  '',     ''),
    ('Sony TV',  '192.168.100.43', 8080, 'http', 'kodi', 'hermes'),
]

# Common KODI userdata paths to probe
SETTINGS_CANDIDATES = [
    '.kodi/userdata/addon_data/pvr.iptvsimple/settings.xml',
    'special://userdata/addon_data/pvr.iptvsimple/settings.xml',
]


def list_dir_via_kodi(api, path):
    """Try Files.GetDirectory on a path. Returns the file list or None."""
    r = api.files_get_directory(path)
    if not r or 'result' not in r:
        return None
    return r['result'].get('files', [])


def get_text_via_kodi(api, path):
    """KODI has no 'get file contents' RPC. For local files we'd need
    to read via the OS. Best-effort: try Files.GetDirectory (works for
    directories) and report the path. The user can paste the file if
    we can't read it remotely."""
    r = api.files_get_directory(path)
    return r


def parse_m3u_local(path):
    """Parse an m3u file and return list of (label, catchup_source, stream_url)."""
    out = []
    if not os.path.exists(path):
        return out
    label = None
    catchup = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.rstrip('\n').rstrip('\r')
            if line.startswith('#EXTINF'):
                # Try to extract tvg-name and catchup-source
                m = re.search(r'tvg-name="([^"]*)"', line)
                label = m.group(1) if m else line.rsplit(',', 1)[-1]
                m = re.search(r'catchup-source="([^"]*)"', line)
                catchup = m.group(1) if m else None
            elif line and not line.startswith('#'):
                out.append((label or '', catchup, line))
                label = None
                catchup = None
    return out


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ({host}:{port}, {proto}) ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        v = api.get_version()
        if not v or 'result' not in v:
            print('  cannot connect')
            continue

        # Try the special:// path first
        for cand in SETTINGS_CANDIDATES:
            r = get_text_via_kodi(api, cand)
            if r and 'result' in r:
                files = r['result'].get('files', [])
                if files:
                    print(f'  found {cand}: {len(files)} entries')
                    for f in files[:10]:
                        print(f'    [{f.get("filetype")}] {f.get("label")!r}  {f.get("file")!r}')
                    break
            else:
                print(f'  cannot list {cand}: {r.get("error", r) if r else "no response"}')

        # Show some local files for context
        print('\n  Files.GetDirectory of C:/ and common userdata roots:')
        for p in ['C:/', 'C:/Users', 'special://home', 'special://userdata']:
            r = get_text_via_kodi(api, p)
            if r and 'result' in r and r['result'].get('files'):
                print(f'    {p}: {len(r["result"]["files"])} entries')

        # We can't read file contents via JSON-RPC, so the user will
        # need to either:
        #  (a) paste the m3u path so we can read it locally
        #  (b) paste the m3u contents
        print('\n  -> ask user for m3u path or contents for this box')


if __name__ == '__main__':
    main()
