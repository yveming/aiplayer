#!/usr/bin/env python3
"""
Offline smoke test of movie search logic with various directory structures:
  - Flat:        movie/Avatar.mkv
  - Year dir:    movie/Avatar (2009)/Avatar.mkv
  - Genre dir:   movie/Sci-Fi/Avatar (2009)/Avatar.mkv
  - Chinese:     movie/阿凡达 (2009)/阿凡达.mkv
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from aiplayer.search_play import search_remote_directory


class MockKodiAPI:
    TREE = {
        'nfs://192.168.100.2/Public/movie/': [
            # Flat files
            {'filetype': 'file', 'label': '独立日.mkv', 'file': 'nfs://192.168.100.2/Public/movie/独立日.mkv'},
            # Year dir (no genre)
            {'filetype': 'directory', 'label': '阿凡达 (2009)',
             'file': 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/'},
            # Genre + year
            {'filetype': 'directory', 'label': '科幻',
             'file': 'nfs://192.168.100.2/Public/movie/科幻/'},
            # Chinese named movie
            {'filetype': 'directory', 'label': '关于约会的一切',
             'file': 'nfs://192.168.100.2/Public/movie/关于约会的一切/'},
        ],
        'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/': [
            {'filetype': 'file', 'label': 'Avatar.2009.2160p.BluRay.x264.mkv',
             'file': 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.2160p.BluRay.x264.mkv'},
            {'filetype': 'file', 'label': 'Avatar.2009.1080p.WEB-DL.mkv',
             'file': 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.1080p.WEB-DL.mkv'},
        ],
        'nfs://192.168.100.2/Public/movie/科幻/': [
            {'filetype': 'directory', 'label': '银翼杀手 2049 (2017)',
             'file': 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/'},
        ],
        'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/': [
            {'filetype': 'file', 'label': 'Blade.Runner.2049.2017.2160p.UHD.BluRay.mkv',
             'file': 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/Blade.Runner.2049.2017.2160p.UHD.BluRay.mkv'},
        ],
        'nfs://192.168.100.2/Public/movie/关于约会的一切/': [
            {'filetype': 'file', 'label': '关于约会的一切.2023.1080p.WEB-DL.mkv',
             'file': 'nfs://192.168.100.2/Public/movie/关于约会的一切/关于约会的一切.2023.1080p.WEB-DL.mkv'},
        ],
    }

    def files_get_directory(self, path):
        return {'result': {'files': self.TREE.get(path, [])}}


def run_test(name, query, expected_paths):
    print(f'\n=== Test: {name} ===')
    print(f'  query: {query!r}')
    api = MockKodiAPI()
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/movie/', query, max_depth=10, debug=True)
    print(f'  matches: {len(matches)}')
    for m in matches:
        print(f'    - [{m["type"]}] {m.get("display", m["label"])}')
    actual_paths = {m['file'] for m in matches}
    expected_set = set(expected_paths)
    if actual_paths == expected_set:
        print('  PASS')
    else:
        print('  FAIL')
        print(f'  expected: {sorted(expected_set)}')
        print(f'  actual:   {sorted(actual_paths)}')


if __name__ == '__main__':
    # Test 1: flat file search
    run_test('Flat file - "独立日"',
             '独立日',
             [
                 'nfs://192.168.100.2/Public/movie/独立日.mkv',
             ])

    # Test 2: movie in year dir
    run_test('Year dir - "阿凡达"',
             '阿凡达',
             [
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/',
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.2160p.BluRay.x264.mkv',
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.1080p.WEB-DL.mkv',
             ])

    # Test 3: multi-level (genre + year)
    run_test('Genre + year - "银翼杀手"',
             '银翼杀手',
             [
                 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/',
                 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/Blade.Runner.2049.2017.2160p.UHD.BluRay.mkv',
             ])

    # Test 4: long Chinese title (no particles, no 的)
    run_test('Long Chinese title - "关于约会的一切"',
             '关于约会的一切',
             [
                 'nfs://192.168.100.2/Public/movie/关于约会的一切/',
                 'nfs://192.168.100.2/Public/movie/关于约会的一切/关于约会的一切.2023.1080p.WEB-DL.mkv',
             ])

    # Test 5: query with year
    run_test('With year - "阿凡达 2009"',
             '阿凡达2009',
             [
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/',
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.2160p.BluRay.x264.mkv',
                 'nfs://192.168.100.2/Public/movie/阿凡达 (2009)/Avatar.2009.1080p.WEB-DL.mkv',
             ])

    # Test 6: query that matches a sub-string across genre and movie
    run_test('Across genre - "科幻"',
             '科幻',
             [
                 'nfs://192.168.100.2/Public/movie/科幻/',
                 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/',
                 'nfs://192.168.100.2/Public/movie/科幻/银翼杀手 2049 (2017)/Blade.Runner.2049.2017.2160p.UHD.BluRay.mkv',
             ])
