#!/usr/bin/env python3
"""Priority rule checks: CLI args > config file > derived sources.

- EPG source: --epg > config iptv.epg > m3u x-tvg-url
- mpv path:   --mpv-path > config mpv.path > PATH lookup > error
"""
import io, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import aiplayer.pvr_epg as pvr_epg
from aiplayer.player import PlayerMode
from aiplayer.player_factory import create_player

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS %s' % name)
    else:
        failed += 1
        print('  FAIL %s %s' % (name, detail))


M3U = '#EXTM3U x-tvg-url="http://m3u-epg"\n'

real_load_config = pvr_epg.load_config
try:
    pvr_epg.load_config = lambda: {'iptv': {'epg': 'http://config-epg'}}
    check('CLI --epg wins over config',
          pvr_epg._resolve_epg_source(None, 'http://cli-epg') == 'http://cli-epg')
    check('CLI --epg wins over config + m3u',
          pvr_epg._resolve_epg_source(M3U, 'http://cli-epg') == 'http://cli-epg')
    check('config beats m3u x-tvg-url',
          pvr_epg._resolve_epg_source(M3U, None) == 'http://config-epg')

    pvr_epg.load_config = lambda: {'iptv': {'epg': ''}}
    check('empty config falls back to m3u x-tvg-url',
          pvr_epg._resolve_epg_source(M3U, None) == 'http://m3u-epg')

    pvr_epg.load_config = lambda: {'iptv': {}}
    check('nothing configured resolves to None',
          pvr_epg._resolve_epg_source(None, None) is None)
finally:
    pvr_epg.load_config = real_load_config

p = create_player(PlayerMode.LOCAL, local_config={'mpv_path': 'C:/fake/mpv.exe'})
check('mpv_path from local_config used verbatim',
      p.local.mpv_path == 'C:/fake/mpv.exe')

print()
print('TOTAL: %d passed, %d failed' % (passed, failed))
sys.exit(0 if failed == 0 else 1)
