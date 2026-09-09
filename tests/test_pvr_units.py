import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.pvr_epg import parse_time, find_channel_by_name

print('--- parse_time tests ---')
for s in ['2024-12-01T20:00:00.000Z', '2024-12-01T20:00:00+00:00',
          '2024-12-01 20:00:00', 'now', 'today', 'yesterday', 'tomorrow',
          '21:00', '', 'garbage',
          # Chinese keywords (must not regress to mojibake)
          '昨天', '今天', '前天', '明天', '后天', '现在',
          '9点30分', '十点半']:
    dt = parse_time(s)
    print('  parse_time(%-32r) -> %r' % (s, dt))

# hard assertions for the Chinese keywords
from datetime import datetime, timedelta, timezone as _tz
_cn = {'昨天': 1, '今天': 0, '前天': 2, '明天': -1, '后天': -2}
for kw, days_back in _cn.items():
    dt = parse_time(kw, default_tz='local')
    expect = (datetime.now(_tz(timedelta(hours=8))) - timedelta(days=days_back)
              ).replace(hour=0, minute=0, second=0, microsecond=0)
    assert dt is not None and dt.astimezone(_tz(timedelta(hours=8))) == expect, (
        'parse_time(%r) broken: %r' % (kw, dt))
print('  Chinese date keywords: asserted OK')

print()
print('--- find_channel_by_name tests ---')
chans = [
    {'label': '湖南卫视', 'channelid': 1},
    {'label': 'CCTV-1 综合', 'channelid': 2},
    {'label': 'CCTV-5 体育', 'channelid': 3},
    {'label': '凤凰卫视中文台', 'channelid': 4},
]
for q in ['湖南卫视', 'cctv-1', '凤凰', '湖南', 'nonexistent']:
    ch = find_channel_by_name(chans, q)
    print('  find(%-15r) -> %r' % (q, ch.get('label') if ch else None))
