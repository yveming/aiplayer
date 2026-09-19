#!/usr/bin/env python3
"""KodiAPI / KodiBackend contract checks (offline, no KODI needed).

Regression guard for the echo paths that used to call methods which did
not exist on KodiAPI:
  - player_get_item(player_id, properties)   (was missing entirely)
  - player_get_properties(player_id, properties)  (only accepted player_id)
"""
import io, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from aiplayer.kodi_api import KodiAPI
from aiplayer.player_kodi import KodiBackend

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS %s' % name)
    else:
        failed += 1
        print('  FAIL %s %s' % (name, detail))


class FakeKodi:
    """Minimal KodiAPI stand-in for the playback/echo paths."""

    def __init__(self, speed=1, active=True, item=None):
        self.speed = speed
        self.active = active
        self.item = item or {'title': 'Song', 'file': '/m/song.mp3', 'duration': 200}
        self.calls = []

    def player_get_active_players(self):
        return {'result': [{'playerid': 0, 'type': 'audio'}]} if self.active else {'result': []}

    def player_get_item(self, player_id=0, properties=None):
        self.calls.append(('get_item', list(properties or [])))
        return {'result': {'item': dict(self.item)}}

    def player_get_properties(self, player_id=0, properties=None):
        self.calls.append(('get_properties', list(properties or [])))
        return {'result': {
            'time': {'hours': 0, 'minutes': 1, 'seconds': 0},
            'speed': self.speed, 'position': 0, 'playlistid': 0,
        }}

    def player_play_pause(self, player_id=0):
        self.calls.append(('play_pause',))
        return {'result': 'OK'}

    def player_go_to(self, player_id=0, to='next'):
        self.calls.append(('go_to', to))
        return {'result': 'OK'}


def backend_with(fake):
    b = KodiBackend({'host': '127.0.0.1', 'protocol': 'tcp'})
    b.kodi = fake
    return b


# --- KodiAPI surface / signatures -------------------------------------------
check('KodiAPI has player_get_item', hasattr(KodiAPI, 'player_get_item'))
check('KodiAPI has playlist_get_items', hasattr(KodiAPI, 'playlist_get_items'))

api = KodiAPI('1.2.3.4', protocol='http')
captured = []


def record(method, params=None):
    captured.append((method, params))
    return {'result': 'OK'}


api._request = record
api.player_get_properties(0, ['speed'])
check('player_get_properties forwards custom properties',
      captured[-1] == ('Player.GetProperties', {'playerid': 0, 'properties': ['speed']}),
      str(captured[-1]))
api.player_get_properties(0)
check('player_get_properties defaults properties',
      captured[-1][1]['properties'] == ['time', 'totaltime', 'percentage', 'speed', 'volume'])

api.player_get_item(0, ['title', 'file'])
check('player_get_item calls Player.GetItem',
      captured[-1] == ('Player.GetItem', {'playerid': 0, 'properties': ['title', 'file']}),
      str(captured[-1]))

# -32602 fallback: a rejected wide list retries with title/file/duration only.
captured.clear()
resp = iter([{'error': {'code': -32602}}, {'result': {'item': {'title': 'T'}}}])


def fallback(method, params=None):
    captured.append((method, params))
    return next(resp)


api._request = fallback
out = api.player_get_item(0, ['title', 'file', 'artist', 'album'])
check('player_get_item retries minimal props on error',
      out.get('result', {}).get('item', {}).get('title') == 'T' and len(captured) == 2,
      str(captured))
check('fallback drops unsupported props',
      captured[-1][1]['properties'] == ['title', 'file'], str(captured[-1]))

api._request = record
api.playlist_get_items(1, ['title', 'file'])
check('playlist_get_items calls Playlist.GetItems',
      captured[-1] == ('Playlist.GetItems', {'playlistid': 1, 'properties': ['title', 'file']}),
      str(captured[-1]))

# --- KodiBackend echo paths must not raise ----------------------------------
b = backend_with(FakeKodi(speed=1))
st = b.status()
check('status returns title', st.get('title') == 'Song', str(st))
check('status computes time-pos', st.get('time-pos') == 60, str(st))
check('status computes remaining', st.get('remaining') == 140, str(st))
check('current_file returns title', b.current_file() == 'Song')

b = backend_with(FakeKodi(speed=1))
check('play while playing is a no-op', b.control_playback('play') is True)
check('play while playing does not toggle',
      ('play_pause',) not in b.kodi.calls, str(b.kodi.calls))

b = backend_with(FakeKodi(speed=0))
check('pause while paused is a no-op', b.control_playback('pause') is True)
check('pause while paused does not toggle',
      ('play_pause',) not in b.kodi.calls, str(b.kodi.calls))

b = backend_with(FakeKodi(speed=1))
check('next returns OK', b.control_playback('next') is True)
check('next calls Player.GoTo',
      ('go_to', 'next') in b.kodi.calls, str(b.kodi.calls))
check('next echoes current file', ('get_item', ['file', 'title']) in b.kodi.calls,
      str(b.kodi.calls))

print()
print('TOTAL: %d passed, %d failed' % (passed, failed))
sys.exit(0 if failed == 0 else 1)
