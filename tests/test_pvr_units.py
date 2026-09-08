import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.pvr_epg import parse_time, find_channel_by_name

print('--- parse_time tests ---')
for s in ['2024-12-01T20:00:00.000Z', '2024-12-01T20:00:00+00:00',
          '2024-12-01 20:00:00', 'now', 'today', 'yesterday', 'tomorrow',
          '21:00', '', 'garbage']:
    dt = parse_time(s)
    print('  parse_time(%-32r) -> %r' % (s, dt))

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
