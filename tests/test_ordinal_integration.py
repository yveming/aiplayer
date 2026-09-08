#!/usr/bin/env python3
"""Integration test: ordinal movie search against a 3-Avatar movie structure
that mirrors what the user has on G:\\movie\\阿凡达\\.

Layout:
  nfs://192.168.100.2/Public/movie/
    阿凡达/
      Avatar.2009.EXTENDED.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-FGT.mkv
      Avatar.The.Way.of.Water.2022.2160p.WEB-DL.DDP5.1.Atmos.HEVC-CMRG.mkv
      Avatar.Fire.and.Ash.2025.2160p.iTunes.WEB-DL.DDP.7.1.Atmos.DV.H.265-DreamHD.mkv
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.stdout.reconfigure(encoding='utf-8')

from aiplayer.search_play import (
    search_remote_directory, extract_movie_ordinal, strip_movie_ordinal,
    _pick_ordinal_files, extract_movie_year,
)

AVATAR_2009 = 'nfs://192.168.100.2/Public/movie/阿凡达/Avatar.2009.EXTENDED.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-FGT.mkv'
AVATAR_2022 = 'nfs://192.168.100.2/Public/movie/阿凡达/Avatar.The.Way.of.Water.2022.2160p.WEB-DL.DDP5.1.Atmos.HEVC-CMRG.mkv'
AVATAR_2025 = 'nfs://192.168.100.2/Public/movie/阿凡达/Avatar.Fire.and.Ash.2025.2160p.iTunes.WEB-DL.DDP.7.1.Atmos.DV.H.265-DreamHD.mkv'

ALL_THREE = {AVATAR_2009, AVATAR_2022, AVATAR_2025}


class MockKodiAPI:
    TREE = {
        'nfs://192.168.100.2/Public/movie/': [
            {'filetype': 'directory', 'label': '阿凡达',
             'file': 'nfs://192.168.100.2/Public/movie/阿凡达/'},
        ],
        'nfs://192.168.100.2/Public/movie/阿凡达/': [
            {'filetype': 'file', 'label': os.path.basename(AVATAR_2009), 'file': AVATAR_2009},
            {'filetype': 'file', 'label': os.path.basename(AVATAR_2022), 'file': AVATAR_2022},
            {'filetype': 'file', 'label': os.path.basename(AVATAR_2025), 'file': AVATAR_2025},
        ],
    }

    def files_get_directory(self, path):
        return {'result': {'files': self.TREE.get(path, [])}}


def test_no_ordinal_returns_all_three():
    print('\n=== Test: 阿凡达 (no ordinal) -> all 3 files ===')
    api = MockKodiAPI()
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', '阿凡达')
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  matches:', [m.get('label') for m in matches])
    if files == ALL_THREE:
        print('  PASS')
    else:
        print('  FAIL: expected all 3, got', files)
        return False
    return True


def test_ordinal_3_picks_2025():
    print('\n=== Test: 阿凡达三 -> Avatar.Fire.and.Ash.2025...mkv ===')
    api = MockKodiAPI()
    q = '阿凡达三'
    ord_n = extract_movie_ordinal(q)
    base = strip_movie_ordinal(q)
    print(f'  parsed: ord={ord_n}, base={base!r}')
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', base)
    if ord_n:
        matches = _pick_ordinal_files(matches, ord_n)
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  picked:', [m.get('label') for m in matches])
    if files == {AVATAR_2025}:
        print('  PASS')
    else:
        print('  FAIL: expected only', os.path.basename(AVATAR_2025))
        print('        got', {os.path.basename(f) for f in files})
        return False
    return True


def test_ordinal_1_picks_2009():
    print('\n=== Test: 阿凡达一 -> Avatar.2009...mkv ===')
    api = MockKodiAPI()
    q = '阿凡达一'
    ord_n = extract_movie_ordinal(q)
    base = strip_movie_ordinal(q)
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', base)
    matches = _pick_ordinal_files(matches, ord_n)
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  picked:', [m.get('label') for m in matches])
    if files == {AVATAR_2009}:
        print('  PASS')
    else:
        print('  FAIL: expected only', os.path.basename(AVATAR_2009))
        return False
    return True


def test_ordinal_arabic_2_picks_2022():
    print('\n=== Test: 阿凡达 2 -> Avatar.The.Way.of.Water.2022...mkv ===')
    api = MockKodiAPI()
    q = '阿凡达 2'
    ord_n = extract_movie_ordinal(q)
    base = strip_movie_ordinal(q)
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', base)
    matches = _pick_ordinal_files(matches, ord_n)
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  picked:', [m.get('label') for m in matches])
    if files == {AVATAR_2022}:
        print('  PASS')
    else:
        print('  FAIL: expected only', os.path.basename(AVATAR_2022))
        return False
    return True


def test_ordinal_arabic_3_attached():
    print('\n=== Test: 阿凡达3 (no space) -> Avatar.Fire.and.Ash.2025...mkv ===')
    api = MockKodiAPI()
    q = '阿凡达3'
    ord_n = extract_movie_ordinal(q)
    base = strip_movie_ordinal(q)
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', base)
    matches = _pick_ordinal_files(matches, ord_n)
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  picked:', [m.get('label') for m in matches])
    if files == {AVATAR_2025}:
        print('  PASS')
    else:
        print('  FAIL: expected only', os.path.basename(AVATAR_2025))
        return False
    return True


def test_di_picks_3():
    print('\n=== Test: 阿凡达第三部 -> Avatar.Fire.and.Ash.2025...mkv ===')
    api = MockKodiAPI()
    q = '阿凡达第三部'
    ord_n = extract_movie_ordinal(q)
    base = strip_movie_ordinal(q)
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', base)
    matches = _pick_ordinal_files(matches, ord_n)
    files = {m['file'] for m in matches if m['type'] == 'file'}
    print('  picked:', [m.get('label') for m in matches])
    if files == {AVATAR_2025}:
        print('  PASS')
    else:
        print('  FAIL: expected only', os.path.basename(AVATAR_2025))
        return False
    return True


if __name__ == '__main__':
    results = [
        test_no_ordinal_returns_all_three(),
        test_ordinal_3_picks_2025(),
        test_ordinal_1_picks_2009(),
        test_ordinal_arabic_2_picks_2022(),
        test_ordinal_arabic_3_attached(),
        test_di_picks_3(),
    ]
    n_pass = sum(results)
    n_total = len(results)
    print(f'\n{n_pass}/{n_total} tests passed')
    sys.exit(0 if n_pass == n_total else 1)
