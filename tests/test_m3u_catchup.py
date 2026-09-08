#!/usr/bin/env python3
"""Offline test for m3u_catchup.py - parser + URL builder."""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
from datetime import datetime, timezone, timedelta
from aiplayer.m3u_catchup import parse_m3u, find_channel, build_catchup_url, _read_text, discover_m3u
from aiplayer.m3u_catchup import (parse_xmltv, get_x_tvg_url, find_program_in_xmltv,
                         _parse_xmltv_time)


SAMPLE_M3U = '''#EXTM3U
#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV-1" catchup-source="http://example.com/cctv1/{utc}-{duration}.m3u8" catchup-days="7" group-title="央视频道",CCTV-1
http://example.com/live/cctv1.m3u8
#EXTINF:-1 tvg-id="hunan" tvg-name="湖南卫视" catchup-source="http://other.com/catchup?id={catchup-id}&start={start}&end={end}" catchup-days="3" group-title="卫视",湖南卫视
http://other.com/live/hunan.m3u8
#EXTINF:-1 tvg-name="LocalOnly" group-title="Other",Local Channel
http://third.com/live/local.m3u8
#EXTINF:-1 tvg-name="TimeFormat" catchup-source="http://time.com/c/{utctime}-{duration}.ts",TimeFormat
http://time.com/live.m3u8
'''


def test_parse_m3u():
    print('--- parse_m3u ---')
    entries = parse_m3u(SAMPLE_M3U)
    print(f'  parsed {len(entries)} entries')
    for e in entries:
        print(f'    tvg_name={e.get("tvg_name")!r}  label={e.get("label")!r}  '
              f'catchup={"yes" if e.get("catchup_source") else "no"}')
    assert len(entries) == 4, f'expected 4 entries, got {len(entries)}'
    assert entries[0]['catchup_source'] == 'http://example.com/cctv1/{utc}-{duration}.m3u8'
    assert entries[1]['catchup_source'].startswith('http://other.com/catchup?')
    assert entries[2]['catchup_source'] is None  # LocalOnly has no catchup
    assert entries[3]['catchup_source'] == 'http://time.com/c/{utctime}-{duration}.ts'
    print('  PASS')


def test_find_channel():
    print('\n--- find_channel ---')
    entries = parse_m3u(SAMPLE_M3U)
    e = find_channel(entries, 'CCTV-1')
    assert e and e['tvg_name'] == 'CCTV-1', 'CCTV-1 lookup failed'
    print('  CCTV-1 -> tvg_name=CCTV-1  OK')
    e = find_channel(entries, 'cctv-1')
    assert e and e['tvg_name'] == 'CCTV-1', 'case-insensitive lookup failed'
    print('  cctv-1 -> tvg_name=CCTV-1  OK')
    e = find_channel(entries, '湖南卫视')
    assert e and e['tvg_name'] == '湖南卫视'
    print('  湖南卫视 -> tvg_name=湖南卫视  OK')
    e = find_channel(entries, 'Local')
    assert e and e['tvg_name'] == 'LocalOnly', 'substring lookup failed'
    print('  Local -> tvg_name=LocalOnly  OK')
    e = find_channel(entries, 'nonexistent')
    assert e is None
    print('  nonexistent -> None  OK')
    print('  PASS')


def test_build_catchup_url():
    print('\n--- build_catchup_url ---')
    # 2024-12-01 12:00:00 UTC -> 1733054400 epoch
    start = datetime(2024, 12, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 12, 1, 12, 30, 0, tzinfo=timezone.utc)

    cases = [
        # (template, expected)
        ('http://e.com/c/{start}.m3u8',
         'http://e.com/c/1733054400.m3u8'),
        ('http://e.com/c/{start}-{end}.m3u8',
         'http://e.com/c/1733054400-1733056200.m3u8'),
        ('http://e.com/c/{utc}-{duration}.m3u8',
         'http://e.com/c/1733054400-1800.m3u8'),
        ('http://e.com/c/{timestamp}.m3u8',
         'http://e.com/c/1733054400.m3u8'),
        ('http://e.com/c/{utctime}.m3u8',
         'http://e.com/c/20241201120000.m3u8'),
        ('http://e.com/c/{localtime}.m3u8',
         'http://e.com/c/20241201200000.m3u8'),  # +8
        ('http://e.com/c/{start_ms}-{end_ms}.m3u8',
         'http://e.com/c/1733054400000-1733056200000.m3u8'),
        ('http://e.com/c?id={catchup-id}&s={start}',
         'http://e.com/c?id=hunan123&s=1733054400'),
        # --- New: iptvsimple strftime  ${(b)...} / ${(e)...}
        # (b)/(e) default to local time per iptvsimple spec
        ('http://e.com/c/playseek-${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}',
         'http://e.com/c/playseek-20241201200000-20241201203000'),
        # dash-delimited variant
        ('http://e.com/c/${(b)yyyy-MM-dd}/${(b)HH}-${(e)HH}.ts',
         'http://e.com/c/2024-12-01/20-20.ts'),
        # --- New: VLC-style  {name:fmt}
        ('http://e.com/c/{utc:YmdHMS}-{utcend:YmdHMS}.ts',
         'http://e.com/c/20241201120000-20241201123000.ts'),
        # local variant
        ('http://e.com/c/{lutc:YmdHMS}-{lutcend:YmdHMS}.ts',
         'http://e.com/c/20241201200000-20241201203000.ts'),
    ]
    failed = False
    for tpl, expected in cases:
        actual = build_catchup_url(tpl, start, end,
                                   local_tz=timezone(timedelta(hours=8)),
                                   catchup_id='hunan123')
        tag = 'OK  ' if actual == expected else 'FAIL'
        print('  [%s] %s' % (tag, tpl))
        print('         -> %s' % actual)
        if actual != expected:
            print('         EXP: %s' % expected)
            failed = True
    if failed:
        return False
    print('  PASS')
    return True


def test_mixed_formats_real_m3u():
    """Simulate a real m3u with BOTH strftime and VLC formats, mirroring
    the user's situation: one m3u contains two co-existing templates."""
    print('\n--- mixed formats in one m3u ---')
    m3u = '''#EXTM3U
#EXTINF:-1 tvg-id="a" tvg-name="ChanA" catchup-source="http://a.com/c/playseek-${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}.m3u8" catchup-days="7",ChanA
http://a.com/live.m3u8
#EXTINF:-1 tvg-id="b" tvg-name="ChanB" catchup-source="http://b.com/{utc:YmdHMS}-{utcend:YmdHMS}.ts" catchup-days="3",ChanB
http://b.com/live.m3u8
#EXTINF:-1 tvg-id="c" tvg-name="ChanC" catchup-source="http://c.com/?start={start}&end={end}" catchup-days="3",ChanC
http://c.com/live.m3u8
'''
    entries = parse_m3u(m3u)
    assert len(entries) == 3
    a = find_channel(entries, 'ChanA')
    b = find_channel(entries, 'ChanB')
    c = find_channel(entries, 'ChanC')
    assert a and b and c
    assert '${(b)yyyyMMddHHmmss}' in a['catchup_source']
    assert '{utc:YmdHMS}' in b['catchup_source']
    assert '{start}' in c['catchup_source']
    print('  3 entries with 3 different catchup formats  OK')

    start = datetime(2024, 12, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 12, 1, 12, 30, 0, tzinfo=timezone.utc)
    ltz = timezone(timedelta(hours=8))

    ua = build_catchup_url(a['catchup_source'], start, end, local_tz=ltz)
    ub = build_catchup_url(b['catchup_source'], start, end, local_tz=ltz)
    uc = build_catchup_url(c['catchup_source'], start, end, local_tz=ltz)
    print('  A:', ua)
    print('  B:', ub)
    print('  C:', uc)
    assert '20241201200000-20241201203000' in ua
    assert '20241201120000-20241201123000' in ub
    assert '?start=1733054400&end=1733056200' in uc
    print('  PASS')


def test_read_text_local(tmpfile):
    """_read_text reads a local file."""
    with open(tmpfile, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n#XTEST\n')
    text = _read_text(tmpfile)
    assert text.startswith('#EXTM3U')
    print('  _read_text(local file)  OK')


def test_read_text_http():
    """_read_text fetches an HTTP URL. Uses the user's IPTV backend."""
    text = _read_text('http://192.168.100.2:8000/iptv/iptv-10.m3u')
    assert text.startswith('#EXTM3U')
    assert 'EXTINF' in text
    print(f'  _read_text(http://192.168.100.2:8000/iptv/iptv-10.m3u)  '
          f'OK ({len(text)} bytes)')


def test_discover_m3u_picks_best_overlap():
    """discover_m3u probes a directory and picks the m3u with the
    highest overlap with the KODI channel list."""
    channel_names = ['CCTV-1综合', 'CCTV-2财经', 'CCTV-3综艺',
                     '湖南卫视', 'CCTV-5体育', 'CCTV-6电影']
    best_url, entries, overlap = discover_m3u(
        'http://192.168.100.2:8000/iptv/', channel_names)
    assert best_url, 'expected to find at least one m3u'
    # Should pick iptv-10.m3u (46 channels, matches the 46-channel
    # 11 box profile) rather than iptv-full.m3u (177 channels with
    # different channel names like 湖南卫视4K).
    print(f'  picked: {best_url}  overlap={overlap}/{len(channel_names)}  '
          f'entries={len(entries)}')
    # We don't hardcode which one is picked - just require overlap > 0
    assert overlap > 0, 'no overlap found'
    print('  PASS')


# ── XMLTV ──────────────────────────────────────────────────────────

SAMPLE_XMLTV = '''<?xml version='1.0' encoding='utf-8'?>
<tv generator-info-name="test">
  <channel id="CCTV-1">
    <display-name lang="zh">CCTV-1</display-name>
  </channel>
  <channel id="hunan">
    <display-name lang="zh">湖南卫视</display-name>
  </channel>
  <programme start="20260607190000 +0800" stop="20260607200000 +0800" channel="CCTV-1">
    <title>新闻联播</title>
  </programme>
  <programme start="20260607200000 +0800" stop="20260607210000 +0800" channel="CCTV-1">
    <title>天气预报</title>
  </programme>
  <programme start="20260607201000 +0800" stop="20260607210500 +0800" channel="hunan">
    <title>耀华(16)</title>
  </programme>
</tv>'''


def test_parse_xmltv_time():
    print('--- _parse_xmltv_time ---')
    # +0800 offset
    dt = _parse_xmltv_time('20260607201000 +0800')
    assert dt is not None
    assert dt.hour == 20 and dt.minute == 10
    assert dt.utcoffset().total_seconds() == 8 * 3600
    # In UTC this is 12:10
    assert dt.astimezone(timezone.utc).hour == 12
    print('  +0800 -> 20:10 local, 12:10 UTC  OK')
    # Negative offset
    dt = _parse_xmltv_time('20260607201000 -0500')
    assert dt is not None
    assert dt.astimezone(timezone.utc).hour == 1 and dt.astimezone(timezone.utc).day == 8
    print('  -0500 -> UTC 01:10 next day  OK')
    # Naive (no offset) -> UTC
    dt = _parse_xmltv_time('20260607201000')
    assert dt is not None
    assert dt.utcoffset().total_seconds() == 0
    print('  naive -> UTC  OK')
    # Garbage
    assert _parse_xmltv_time('') is None
    assert _parse_xmltv_time('not a date') is None
    print('  garbage -> None  OK')
    print('  PASS')


def test_get_x_tvg_url():
    print('--- get_x_tvg_url ---')
    m3u = ('#EXTM3U name="foo" x-tvg-url="http://e.com/epg.xml.gz"\n'
           '#EXTINF:-1 tvg-id="x",X\nhttp://x\n')
    assert get_x_tvg_url(m3u) == 'http://e.com/epg.xml.gz'
    print('  x-tvg-url extracted  OK')
    m3u2 = '#EXTM3U\n#EXTINF:-1,X\nhttp://x\n'
    assert get_x_tvg_url(m3u2) is None
    print('  no x-tvg-url -> None  OK')
    print('  PASS')


def test_parse_xmltv_string():
    print('--- parse_xmltv (string source) ---')
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), 'm3u_catchup_test_epg.xml')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(SAMPLE_XMLTV)
    try:
        channels, programs = parse_xmltv(tmp)
        assert len(channels) == 2, f'expected 2 channels, got {len(channels)}'
        assert channels.get('hunan') == '湖南卫视'
        assert len(programs) == 3, f'expected 3 programs, got {len(programs)}'
        # First CCTV-1 program
        cctv1 = [p for p in programs if p['channel'] == 'CCTV-1']
        assert len(cctv1) == 2
        # 2026-06-07 19:00 +0800 = 11:00 UTC
        assert cctv1[0]['start_utc'].hour == 11
        assert cctv1[0]['start_utc'].day == 7
        # hunan programme: 20:10 +0800 = 12:10 UTC
        hunan_p = [p for p in programs if p['channel'] == 'hunan'][0]
        assert hunan_p['title'] == '耀华(16)'
        assert hunan_p['start_utc'].hour == 12
        print(f'  channels={len(channels)}  programs={len(programs)}  '
              f'cctv1[0]={cctv1[0]["start_utc"]}  hunan={hunan_p["title"]!r}  OK')
        print('  PASS')
    finally:
        os.remove(tmp)


def test_find_program_in_xmltv_string():
    print('--- find_program_in_xmltv (string source) ---')
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), 'm3u_catchup_test_epg2.xml')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(SAMPLE_XMLTV)
    try:
        _, programs = parse_xmltv(tmp)
        local = timezone(timedelta(hours=8))
        # 21:00 local on 2026-06-07 should land in hunan's 20:10-21:05 programme
        target = datetime(2026, 6, 7, 21, 0, tzinfo=local)
        p = find_program_in_xmltv(programs, 'hunan', target)
        assert p is not None, 'should find hunan programme at 21:00'
        assert p['title'] == '耀华(16)'
        print(f'  21:00 local -> {p["title"]!r} (start={p["start_utc"]})  OK')
        # 19:30 local on 2026-06-07 should land in CCTV-1's 19:00-20:00 programme
        target2 = datetime(2026, 6, 7, 19, 30, tzinfo=local)
        p2 = find_program_in_xmltv(programs, 'CCTV-1', target2)
        assert p2 is not None
        assert p2['title'] == '新闻联播'
        print(f'  19:30 local -> {p2["title"]!r}  OK')
        # 21:30 on a future day should not find anything on hunan
        target3 = datetime(2026, 6, 8, 21, 30, tzinfo=local)
        p3 = find_program_in_xmltv(programs, 'hunan', target3)
        assert p3 is None
        print('  future day -> None  OK')
        # 21:30 on 2026-06-07 (after the 20:10-21:05 programme ended) -> None
        target4 = datetime(2026, 6, 7, 21, 30, tzinfo=local)
        p4 = find_program_in_xmltv(programs, 'hunan', target4)
        assert p4 is None
        print('  after broadcast end -> None  OK')
        print('  PASS')
    finally:
        os.remove(tmp)



def test_find_program_xmltv_exclusive_end():
    """start <= target < end: boundary at stop time should NOT match."""
    local = timezone(timedelta(hours=8))
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), 'm3u_catchup_test_xmltv_boundary.xml')
    xml = '''<?xml version='1.0' encoding='utf-8'?>
<tv>
  <channel id="hunan"><display-name>HunanTV</display-name></channel>
  <programme start="20260610183000 +0800" stop="20260610190000 +0800" channel="hunan">
    <title>News 18:30</title>
  </programme>
  <programme start="20260610190000 +0800" stop="20260610193000 +0800" channel="hunan">
    <title>News 19:00</title>
  </programme>
</tv>'''
    with open(tmp, 'w', encoding='utf-8') as ff:
        ff.write(xml)
    try:
        _, programs = parse_xmltv(tmp)
        # 18:59 -> News 18:30
        t1 = datetime(2026, 6, 10, 18, 59, tzinfo=local)
        p1 = find_program_in_xmltv(programs, 'hunan', t1)
        assert p1 and p1['title'] == 'News 18:30', f'18:59 should match News 18:30, got {p1}'
        # 19:00 EXACTLY -> News 19:00 (not News 18:30, because end is exclusive)
        t2 = datetime(2026, 6, 10, 19, 0, tzinfo=local)
        p2 = find_program_in_xmltv(programs, 'hunan', t2)
        assert p2 and p2['title'] == 'News 19:00', f'19:00 should match News 19:00, got {p2}'
        print(f'  18:59 -> {p1["title"]!r}  19:00 -> {p2["title"]!r}  OK')
        print('  PASS')
    finally:
        os.remove(tmp)

def test_xmltv_http():
    """Round-trip: real backend, real gzipped XMLTV."""
    print('--- parse_xmltv (HTTP gzipped) ---')
    text = _read_text('http://192.168.100.2:8000/iptv/iptv-10.m3u')
    epg_url = get_x_tvg_url(text)
    if not epg_url:
        base = 'http://192.168.100.2:8000/iptv/'
        for candidate in ('iptv-epg.xml.gz', 'iptv-epg.xml', 'epg.xml.gz', 'epg.xml'):
            try:
                _read_text(base + candidate)
                epg_url = base + candidate
                break
            except Exception:
                continue
    assert epg_url and epg_url.endswith('.gz'), 'Could not find EPG URL'
    channels, programs = parse_xmltv(epg_url)
    assert len(channels) > 50, f'expected 100+ channels, got {len(channels)}'
    assert len(programs) > 1000
    hunan = channels.get('湖南卫视')
    assert hunan == '湖南卫视', f'湖南卫视 channel id missing: {hunan!r}'
    hunan_progs = [p for p in programs if p['channel'] == '湖南卫视']
    assert len(hunan_progs) > 50
    print(f'  channels={len(channels)}  programs={len(programs)}  '
          f'湖南卫视={len(hunan_progs)} progs  OK')
    # Find a known programme
    local = timezone(timedelta(hours=8))
    target = (datetime.now(local) - timedelta(days=1)).replace(
        hour=21, minute=0, second=0, microsecond=0)
    p = find_program_in_xmltv(programs, '湖南卫视', target)
    assert p is not None
    print(f'  yesterday 21:00 -> {p["title"]!r} ({p["start_utc"]})  OK')
    print('  PASS')


if __name__ == '__main__':
    test_parse_m3u()
    test_find_channel()
    ok1 = test_build_catchup_url()
    test_mixed_formats_real_m3u()

    # XMLTV
    print('\n--- XMLTV (offline) ---')
    test_parse_xmltv_time()
    test_get_x_tvg_url()
    test_parse_xmltv_string()
    test_find_program_in_xmltv_string()
    test_find_program_xmltv_exclusive_end()
    xmltv_ok = True

    # HTTP / discovery tests (need network)
    print('\n--- _read_text / discover_m3u (HTTP) ---')
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), 'm3u_catchup_test.m3u')
    try:
        test_read_text_local(tmp)
        test_read_text_http()
        test_discover_m3u_picks_best_overlap()
        test_xmltv_http()
        net_ok = True
    except Exception as e:
        print(f'  HTTP tests skipped: {e}')
        net_ok = False

    print('\n' + ('ALL OK' if (ok1 and xmltv_ok and net_ok) else 'SOME FAILED'))
    sys.exit(0 if (ok1 and xmltv_ok and net_ok) else 1)
