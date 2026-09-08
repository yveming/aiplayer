import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from aiplayer.search_play import extract_movie_ordinal, strip_movie_ordinal

cases = [
    ('阿凡达三', 3, '阿凡达'),
    ('阿凡达第三部', 3, '阿凡达'),
    ('阿凡达 第3部', 3, '阿凡达'),
    ('阿凡达3', 3, '阿凡达'),
    ('阿凡达 3', 3, '阿凡达'),
    ('复仇者联盟四', 4, '复仇者联盟'),
    ('复仇者联盟 第四部', 4, '复仇者联盟'),
    ('阿凡达', None, '阿凡达'),
    ('七宗罪', None, '七宗罪'),
    ('', None, ''),
    ('Avatar 2', 2, 'Avatar'),
    ('蝙蝠侠 7', 7, '蝙蝠侠'),
    ('阿凡达2009', None, '阿凡达2009'),
    ('2001太空漫游', None, '2001太空漫游'),
]
all_ok = True
for q, exp_ord, exp_base in cases:
    o = extract_movie_ordinal(q)
    b = strip_movie_ordinal(q)
    ok_o = o == exp_ord
    ok_b = b == exp_base
    if not (ok_o and ok_b): all_ok = False
    tag_o = 'OK  ' if ok_o else 'FAIL'
    tag_b = 'OK  ' if ok_b else 'FAIL'
    print('  [%s/%s]  ord=%r base=%-20r  q=%r' % (tag_o, tag_b, o, b, q))
print('ALL OK' if all_ok else 'SOME FAILED')
