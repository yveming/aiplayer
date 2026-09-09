#!/usr/bin/env python3
"""Offline tests: KODI no-EPG catchup/epg patch + m3u scoping matrix."""
import io
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.pvr_epg import play_catchup, show_epg
from aiplayer.aiplayer import _m3u_for_tv

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    print('  [%s / %s] %s' % ('OK' if cond else 'FAIL', 'OK' if cond else 'NG', name))
    if cond:
        PASS += 1
    else:
        FAIL += 1


class MockKodi(KodiAPI):
    """PVR box that lists channels but returns NO EPG broadcasts."""

    def __init__(self):
        pass

    def pvr_get_channel_groups(self):
        return {'result': {'channelgroups': [{'channelgroupid': 1, 'label': 'All TV'}]}}

    def pvr_get_channels(self, channel_group_id=1, fields=None, limits=None):
        return {'result': {'channels': [{'channelid': 7, 'label': 'CCTV-1'}]}}

    def pvr_get_broadcasts(self, channel_id, fields=None, limits=None):
        return {}  # box without catch-up support: no EPG

    def play_url(self, url):
        self.played_url = url
        return {'result': 'OK'}


def make_fixtures(tmp):
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    yest = now - timedelta(days=1)
    m3u = os.path.join(tmp, 'iptv.m3u')
    io.open(m3u, 'w', encoding='utf-8').write(
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV1" '
        'catchup="1" catchup-source="http://example.com/cctv1?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}",CCTV-1\n'
        'http://example.com/cctv1\n')
    xml = os.path.join(tmp, 'epg.xml')
    io.open(xml, 'w', encoding='utf-8').write(
        '<tv>\n<channel id="cctv1"><display-name>CCTV-1</display-name></channel>\n'
        '<programme start="%s" stop="%s" channel="cctv1"><title>Evening News</title></programme>\n'
        '</tv>\n' % (
            (yest.replace(hour=20, minute=0, second=0)).strftime('%Y%m%d%H%M%S') + ' +0800',
            (yest.replace(hour=22, minute=0, second=0)).strftime('%Y%m%d%H%M%S') + ' +0800'))
    return m3u, xml


def test_catchup_patch(tmp):
    print('=== play_catchup: KODI no-EPG -> m3u/XMLTV patch ===')
    m3u, xml = make_fixtures(tmp)
    api = MockKodi()
    buf = io.StringIO()
    class Cap:
        def write(self, t): buf.write(t)
        def flush(self): pass
    old = sys.stdout
    sys.stdout = Cap()
    try:
        ok = play_catchup(api, 'CCTV-1', 'yesterday', '21:00', m3u=m3u, epg=xml)
    finally:
        sys.stdout = old
    out = buf.getvalue()
    check('patch triggered', 'falling back to m3u/XMLTV catch-up patch' in out)
    check('success', ok is True)
    url = getattr(api, 'played_url', '')
    check('catchup URL built', url.startswith('http://example.com/cctv1?playseek=') and len(url) > 60)
    check('URL has time range', url.count('20') >= 2 or '21' in url or '22' in url)


def test_catchup_utc_named_template_local_fill(tmp):
    print('=== play_catchup: {utc:}-named template fills LOCAL (mirrors KODI) ===')
    m3u, xml = make_fixtures(tmp)
    s = io.open(m3u, encoding='utf-8').read()
    s = s.replace(
        'catchup-source="http://example.com/cctv1?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"',
        'catchup-source="http://example.com/cctv1?playseek={utc:YmdHMS}-{utcend:YmdHMS}"')
    io.open(m3u, 'w', encoding='utf-8').write(s)
    api = MockKodi()
    buf = io.StringIO()
    class Cap:
        def write(self, t): buf.write(t)
        def flush(self): pass
    old = sys.stdout
    sys.stdout = Cap()
    try:
        ok = play_catchup(api, 'CCTV-1', 'yesterday', '21:00', m3u=m3u, epg=xml)
    finally:
        sys.stdout = old
    out = buf.getvalue()
    url = getattr(api, 'played_url', '')
    tz = timezone(timedelta(hours=8))
    yest = (datetime.now(tz) - timedelta(days=1)).strftime('%Y%m%d')
    check('patch triggered', 'falling back to m3u/XMLTV catch-up patch' in out)
    check('local start filled (200000 not 120000)', (yest + '200000') in url)
    check('local end filled (220000 not 140000)', (yest + '220000') in url)
    check('success', ok is True)


def test_epg_patch(tmp):
    print('=== show_epg: KODI no-EPG -> m3u/XMLTV patch (config m3u fallback) ===')
    m3u, xml = make_fixtures(tmp)
    # config iptv.m3u points at the local m3u; no --m3u passed
    import tempfile
    home = tempfile.mkdtemp(prefix='aiplayer_patch_test_')
    cfgdir = os.path.join(home, '.config', 'aiplayer')
    os.makedirs(cfgdir, exist_ok=True)
    io.open(os.path.join(cfgdir, 'config.json'), 'w', encoding='utf-8').write(
        '{"iptv": {"m3u": %s, "epg": ""}, "metadata": {"enabled": false}}' % (
            '"' + m3u.replace('\\', '\\\\') + '"'))
    old_home = (os.environ.get('USERPROFILE'), os.environ.get('HOME'))
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    try:
        api = MockKodi()
        buf = io.StringIO()
        class Cap:
            def write(self, t): buf.write(t)
            def flush(self): pass
        old = sys.stdout
        sys.stdout = Cap()
        try:
            ok = show_epg(api, 'CCTV-1', 'yesterday', '21:00', m3u=None, epg=xml)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        check('epg patch triggered', 'falling back to m3u/XMLTV EPG patch' in out)
        check('programme shown', 'Evening News' in out)
        check('success', ok is True)
    finally:
        if old_home[0]: os.environ['USERPROFILE'] = old_home[0]
        if old_home[1]: os.environ['HOME'] = old_home[1]


def test_m3u_for_tv_matrix():
    print('=== _m3u_for_tv scoping matrix ===')
    check('local + config -> config', _m3u_for_tv(None, 'cfg-m3u', kodi_mode=False) == 'cfg-m3u')
    check('local + explicit -> explicit', _m3u_for_tv('cli-m3u', 'cfg-m3u', kodi_mode=False) == 'cli-m3u')
    check('kodi + config -> None (no hijack)', _m3u_for_tv(None, 'cfg-m3u', kodi_mode=True) is None)
    check('kodi + explicit -> explicit', _m3u_for_tv('cli-m3u', 'cfg-m3u', kodi_mode=True) == 'cli-m3u')


def main():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='aiplayer_tv_patch_')
    test_m3u_for_tv_matrix()
    test_catchup_patch(tmp)
    test_catchup_utc_named_template_local_fill(tmp)
    test_epg_patch(tmp)
    print()
    print('TOTAL: %d passed, %d failed' % (PASS, FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == '__main__':
    main()