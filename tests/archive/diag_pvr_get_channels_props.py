#!/usr/bin/env python3
"""PVR.GetChannels accepts a different (wider) property set than
PVR.GetChannelDetails.  KODI v21's PVR channel Field enum includes
catchup-source / catchup-days / catchup-modes etc.  The user says
catchup-source IS exposed by PVR.GetChannels on the IPTV Simple
Client - we just need to ask for it as a property.

Probe one property at a time, on both boxes, for PVR.GetChannels.
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

# New property names to try.  We try on PVR.GetChannels (the bulk
# listing) because the user said the catchup-source field comes
# from there, not from GetChannelDetails.
CATCHUP_PROPS = [
    'channel', 'channelnumber',
    'channelid', 'label', 'channeltype', 'hidden', 'locked',
    'thumbnail', 'lastplayed', 'uniqueid', 'clientid',
    'inputstreamclass', 'isrecording', 'isradio',
    # Catch-up fields (the ones we want)
    'streamurl', 'url', 'channelurl',
    'catchupsource', 'catchup-source',
    'catchupdays', 'catchup-days',
    'catchupmodes', 'catchup-modes',
    'catchupdefault', 'catchup-default',
    'catchupcount', 'catchup-count',
    'catchupurlparameter', 'catchupcorrection',
    'catchupid', 'catchup-id', 'catchupprovider',
    'epgid',
    # Maybe these were mis-spelled in our earlier probe
    'catchup_source', 'catchup_days', 'catchup_modes',
    'catch_up_source', 'catch_up_days',
]


def main():
    for name, host, port, proto, user, pwd in TARGETS:
        print(f'\n========== {name} ==========')
        api = KodiAPI(host=host, port=port, protocol=proto,
                      username=user, password=pwd)
        if not api.get_version():
            print('  cannot connect')
            continue

        # First, find 湖南卫视's channelid via the standard lookup
        chs_resp = api.pvr_get_channels(channel_group_id=1,
                                        fields=['channel', 'channelnumber'])
        if not (chs_resp and 'result' in chs_resp):
            print('  no channels')
            continue
        all_chs = chs_resp['result'].get('channels', [])
        target_id = None
        for c in all_chs:
            if c.get('label', '') == '湖南卫视':
                target_id = c.get('channelid')
                break
        print(f'  湖南卫视 id={target_id}  (of {len(all_chs)} total)')

        # Now probe each property one at a time
        for prop in CATCHUP_PROPS:
            r = api.pvr_get_channels(channel_group_id=1, fields=[prop])
            if not (r and 'result' in r):
                err = r.get('error', {}) if r else {}
                print(f'  {prop:30}  ERR {err.get("code")}')
                continue
            chs = r['result'].get('channels', [])
            # Find the value for 湖南卫视 (or first channel)
            target = next((c for c in chs
                           if c.get('channelid') == target_id), None)
            if not target:
                target = chs[0] if chs else None
            if target and prop in target:
                val = target[prop]
                if isinstance(val, str) and len(val) > 80:
                    val = val[:80] + '...'
                print(f'  {prop:30}  {val!r}  '
                      f'(channel: {target.get("label", "?")})')
            else:
                print(f'  {prop:30}  <not in response>')


if __name__ == '__main__':
    main()
