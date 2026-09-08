#!/usr/bin/env python3
"""Try every PVR.GetChannelDetails property that might be related to
catch-up, on both boxes. The user says the m3us use different
catchup-source formats, and we need to know which fields are exposed."""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import get_all_channels, find_channel_by_name

TARGETS = [
    ('11 box',   '192.168.100.11', 9090, 'tcp',  '',     ''),
    ('Sony TV',  '192.168.100.43', 8080, 'http', 'kodi', 'hermes'),
]

# Try the most likely property names one at a time so we can see
# which ones are valid (KODI v21 returns -32602 on the bad ones).
CANDIDATE_PROPS = [
    'streamurl', 'url', 'hascatchup', 'catchupid', 'catchupsource',
    'm3u', 'm3uurl', 'epgurl', 'iconpath', 'thumbnail', 'channeltype',
    'hidden', 'locked', 'displayname', 'channelnumber',
    'inputstreamclass', 'allowimportwatchedstate', 'lastplayed',
    'isrecording', 'recordingpath',
    # extras (round 2)
    'channelurl', 'isradio', 'broadcastid', 'broadcastnextid',
    'subchannelnumber', 'isremovable', 'uniqueid', 'clientid',
    'definition', 'country', 'major', 'minor', 'imagenumber',
    'isuseradded', 'isautoconfigured', 'isvirtual',
    'clientname', 'clientuuid', 'epgcolour', 'mimetype', 'properties',
]


def probe(api, cid, prop):
    r = api.pvr_get_channel_details(cid, properties=[prop])
    if not r:
        return 'NO_RESP'
    if 'error' in r:
        return f'ERR:{r["error"].get("code")}'
    det = r.get('result', {}).get('channeldetails', {})
    val = det.get(prop)
    return val if val is None else f'{val!r}'


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        channels = get_all_channels(api)
        ch = find_channel_by_name(channels, '湖南卫视')
        if not ch:
            print('  no 湖南卫视')
            continue
        cid = ch['channelid']
        print(f'  湖南卫视 id={cid}')

        # Probe each property
        print(f'  {"property":30}  result')
        print('  ' + '-' * 70)
        for p in CANDIDATE_PROPS:
            v = probe(api, cid, p)
            print(f'  {p:30}  {v}')

        # Also try no-properties to see default response
        r = api.pvr_get_channel_details(cid)
        print(f'\n  no properties:')
        print('  ' + json.dumps(r, indent=2, ensure_ascii=False)[:500])


if __name__ == '__main__':
    main()
