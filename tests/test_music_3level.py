#!/usr/bin/env python3
"""
Offline test of music search logic with a 3-level directory structure:
  music/歌手/专辑/歌曲.mp3
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from aiplayer.search_play import search_remote_directory, parse_tv_query, extract_sXXeYY


class MockKodiAPI:
    """Mock KODI API that serves a hardcoded 3-level music directory tree."""
    TREE = {
        'nfs://192.168.100.2/Public/music/': [
            {'filetype': 'directory', 'label': '赵传', 'file': 'nfs://192.168.100.2/Public/music/赵传/'},
            {'filetype': 'directory', 'label': '周杰伦', 'file': 'nfs://192.168.100.2/Public/music/周杰伦/'},
            {'filetype': 'directory', 'label': '李佳薇', 'file': 'nfs://192.168.100.2/Public/music/李佳薇/'},
        ],
        'nfs://192.168.100.2/Public/music/赵传/': [
            {'filetype': 'directory', 'label': '我是一只小小鸟', 'file': 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/'},
            {'filetype': 'directory', 'label': '我终于失去了你', 'file': 'nfs://192.168.100.2/Public/music/赵传/我终于失去了你/'},
        ],
        'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/': [
            {'filetype': 'file', 'label': '我是一只小小鸟.mp3', 'file': 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我是一只小小鸟.mp3'},
            {'filetype': 'file', 'label': '我终于失去了你.mp3', 'file': 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我终于失去了你.mp3'},
            {'filetype': 'file', 'label': '我很丑可是我很温柔.mp3', 'file': 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我很丑可是我很温柔.mp3'},
        ],
        'nfs://192.168.100.2/Public/music/赵传/我终于失去了你/': [
            {'filetype': 'file', 'label': '我终于失去了你.mp3', 'file': 'nfs://192.168.100.2/Public/music/赵传/我终于失去了你/我终于失去了你.mp3'},
        ],
        'nfs://192.168.100.2/Public/music/周杰伦/': [
            {'filetype': 'directory', 'label': '范特西', 'file': 'nfs://192.168.100.2/Public/music/周杰伦/范特西/'},
        ],
        'nfs://192.168.100.2/Public/music/周杰伦/范特西/': [
            {'filetype': 'file', 'label': '双截棍.mp3', 'file': 'nfs://192.168.100.2/Public/music/周杰伦/范特西/双截棍.mp3'},
            {'filetype': 'file', 'label': '爱在西元前.mp3', 'file': 'nfs://192.168.100.2/Public/music/周杰伦/范特西/爱在西元前.mp3'},
        ],
        'nfs://192.168.100.2/Public/music/李佳薇/': [
            {'filetype': 'file', 'label': '煎熬.mp3', 'file': 'nfs://192.168.100.2/Public/music/李佳薇/煎熬.mp3'},
        ],
    }

    def files_get_directory(self, path):
        return {'result': {'files': self.TREE.get(path, [])}}


def run_test(name, query, expected_paths):
    print(f'\n=== Test: {name} ===')
    print(f'  query: {query!r}')
    api = MockKodiAPI()
    matches = search_remote_directory(api, 'nfs://192.168.100.2/Public/music/', query, max_depth=10)
    print(f'  matches: {len(matches)}')
    for m in matches:
        print(f'    - [{m["type"]}] {m.get("display", m["label"])}')
    actual_paths = {m['file'] for m in matches}
    expected_set = set(expected_paths)
    if actual_paths == expected_set:
        print('  PASS')
    else:
        print('  FAIL')
        print(f'  expected: {expected_set}')
        print(f'  actual:   {actual_paths}')


if __name__ == '__main__':
    # Test 1: search by artist only - returns artist dir, all album dirs, and all songs
    run_test('Artist only - "赵传"',
             '赵传',
             [
                 # All directory levels that contain the show name
                 'nfs://192.168.100.2/Public/music/赵传/',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/',
                 'nfs://192.168.100.2/Public/music/赵传/我终于失去了你/',
                 # All songs
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我是一只小小鸟.mp3',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我终于失去了你.mp3',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我很丑可是我很温柔.mp3',
                 'nfs://192.168.100.2/Public/music/赵传/我终于失去了你/我终于失去了你.mp3',
             ])

    # Test 2: search by artist + album (3-level target: album directory)
    run_test('Artist + Album - "赵传 我是一只小小鸟"',
             '赵传我是一只小小鸟',
             [
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我是一只小小鸟.mp3',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我终于失去了你.mp3',
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我很丑可是我很温柔.mp3',
             ])

    # Test 3: search by artist + album + song (full path query)
    run_test('Full path - "赵传我是一只小小鸟的我是一只小小鸟"',
             '赵传我是一只小小鸟的我是一只小小鸟',
             [
                 'nfs://192.168.100.2/Public/music/赵传/我是一只小小鸟/我是一只小小鸟.mp3',
             ])

    # Test 4: search by song only (might be too broad)
    run_test('Song only - "双截棍"',
             '双截棍',
             [
                 'nfs://192.168.100.2/Public/music/周杰伦/范特西/双截棍.mp3',
             ])

    # Test 5: parse_tv_query
    print('\n=== Test: parse_tv_query ===')
    for q in ['黑暗物质 S03E04', '黑暗物质 3x04', '黑暗物质第三季第四集', '黑暗物质']:
        r = parse_tv_query(q)
        print(f'  {q!r:40s} -> show={r["show"]!r}, sXXeYY={r["sXXeYY"]!r}')

    # Test 6: extract_sXXeYY
    print('\n=== Test: extract_sXXeYY ===')
    for label in [
        '黑暗物质.Dark.Matter.S03E04.720p.HDTV.x264.双语字幕精校版-深影字幕组',
        'some.show.s10e20.mkv',
        'NO_PATTERN_HERE.mp4',
    ]:
        print(f'  {label!r:60s} -> {extract_sXXeYY(label)!r}')
