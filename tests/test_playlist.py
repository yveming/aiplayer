#!/usr/bin/env python3
"""Playlist view checks (offline): mpv normalization, KODI Playlist.GetItems,
and CLI formatting. No KODI / mpv required.
"""
import contextlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import aiplayer.local_player as lp
from aiplayer.local_player import MpvPlayer
from aiplayer.player_kodi import KodiBackend
from aiplayer.player_mpv import MpvBackend
from aiplayer.aiplayer import (_print_playlist, _play_files, _remove_from_queue,
                               ACTION_CHOICES, EPILOG)

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS %s' % name)
    else:
        failed += 1
        print('  FAIL %s %s' % (name, detail))


# --- mpv: get_playlist + backend normalization ------------------------------
def fake_cmd(ipc_path, command):
    if command == ["get_property", "idle"]:
        return {"error": "success", "data": False}
    if command == ["get_property", "playlist"]:
        return {"error": "success", "data": [
            {"filename": "/m/a.mp3", "current": False},
            {"filename": "/m/sub/b.mp3", "current": True},
        ]}
    return {"error": "success"}


real_cmd = lp._cmd
lp._cmd = fake_cmd
try:
    p = MpvPlayer.__new__(MpvPlayer)
    p.ipc_path = 'x'
    p._running = True

    raw = p.get_playlist()
    check('mpv get_playlist returns raw entries', len(raw) == 2, str(raw))

    b = MpvBackend.__new__(MpvBackend)
    b.local = p
    entries = b.playlist_items()
    check('mpv backend normalizes index',
          [e['index'] for e in entries] == [0, 1], str(entries))
    check('mpv backend shows basename',
          entries[0]['title'] == 'a.mp3' and entries[1]['title'] == 'b.mp3', str(entries))
    check('mpv backend keeps full path',
          entries[1]['path'] == '/m/sub/b.mp3', str(entries))
    check('mpv backend marks current',
          [e['current'] for e in entries] == [False, True], str(entries))

    # Idle mpv (no IPC) -> empty, and must not raise.
    lp._cmd = lambda ipc, cmd: {"error": "not running"}
    check('idle mpv returns empty queue', p.get_playlist() == [])
finally:
    lp._cmd = real_cmd


# --- KODI: playlist_items via Playlist.GetItems -----------------------------
class FakeKodiPlaylist:
    def __init__(self, active=True, position=1, playlistid=0, items=None):
        self.active = active
        self.position = position
        self.playlistid = playlistid
        self.items = items if items is not None else [
            {'title': 'A', 'file': '/m/a.mp3'},
            {'title': 'B', 'file': '/m/b.mp3'},
        ]

    def player_get_active_players(self):
        if not self.active:
            return {'result': []}
        return {'result': [{'playerid': 0, 'type': 'audio'}]}

    def player_get_properties(self, player_id=0, properties=None):
        result = {}
        if self.position is not None:
            result['position'] = self.position
        if self.playlistid is not None:
            result['playlistid'] = self.playlistid
        return {'result': result}

    def playlist_get_items(self, playlist_id=0, properties=None, limits=None):
        return {'result': {'items': self.items}}


b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiPlaylist()
entries = b.playlist_items()
check('kodi backend title from item', entries[0]['title'] == 'A', str(entries))
check('kodi backend marks current from position',
      [e['current'] for e in entries] == [False, True], str(entries))

b.kodi = FakeKodiPlaylist(position=None)
entries = b.playlist_items()
check('kodi backend no position -> nothing current',
      all(not e['current'] for e in entries), str(entries))

b.kodi = FakeKodiPlaylist(position=None, items=[{'file': '/m/x.mkv'}])
entries = b.playlist_items()
check('kodi backend falls back to basename',
      entries[0]['title'] == 'x.mkv', str(entries))

b.kodi = FakeKodiPlaylist(active=False)
check('kodi backend empty active -> still lists',
      len(b.playlist_items()) == 2)


# --- KODI write ops must target the same playlist as the view ---------------
class FakeKodiWrite(FakeKodiPlaylist):
    def __init__(self, active=True, ptype='audio', playlistid=0):
        super().__init__(active=active, playlistid=playlistid)
        self.ptype = ptype
        self.writes = []
        self.active_calls = 0

    def player_get_active_players(self):
        self.active_calls += 1
        if not self.active:
            return {'result': []}
        return {'result': [{'playerid': 0, 'type': self.ptype}]}

    def playlist_add(self, playlist_id, item):
        self.writes.append(('add', playlist_id))
        return {'result': 'OK'}

    def playlist_clear(self, playlist_id):
        self.writes.append(('clear', playlist_id))
        return {'result': 'OK'}

    def playlist_remove(self, playlist_id, position):
        self.writes.append(('remove', playlist_id, position))
        return {'result': 'OK'}

    def player_open_item(self, item):
        self.writes.append(('open', item))
        return {'result': 'OK'}


b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(ptype='video', playlistid=1)
b.play_file('/m/x.mkv')
b.playlist_append('/m/y.mkv')
check('video append targets playlist 1',
      b.kodi.writes[-1] == ('add', 1), str(b.kodi.writes))

b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(ptype='audio', playlistid=0)
b.play_file('/m/a.mp3')
b.playlist_append('/m/b.mp3')
check('audio append targets playlist 0',
      b.kodi.writes[-1] == ('add', 0), str(b.kodi.writes))

b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(active=False)
b.playlist_clear()
check('clear with no active player defaults to playlist 0',
      b.kodi.writes[-1] == ('clear', 0), str(b.kodi.writes))

b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(ptype='video', playlistid=1)
b.play_file('/m/x.mkv')
b.playlist_append('/m/y1.mkv')
b.playlist_append('/m/y2.mkv')
check('playlist id resolved once per play request',
      b.kodi.active_calls == 1, str(b.kodi.active_calls))

b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(ptype='video', playlistid=1)
b.playlist_play_index(3)
check('play_index opens the resolved playlist',
      b.kodi.writes[-1] == ('open', {'playlistid': 1, 'position': 3}),
      str(b.kodi.writes))

b = KodiBackend.__new__(KodiBackend)
b.kodi = FakeKodiWrite(ptype='video', playlistid=1)
b.play_file('/m/x.mkv')
b.playlist_remove(2)
check('remove targets resolved playlist and position',
      b.kodi.writes[-1] == ('remove', 1, 2), str(b.kodi.writes))


# --- mpv: playlist_remove issues playlist-remove with the index -------------
def fake_remove_cmd(ipc_path, command):
    fake_remove_cmd.seen.append(command)
    if command == ["get_property", "idle"]:
        return {"error": "success", "data": False}
    return {"error": "success"}


fake_remove_cmd.seen = []
lp._cmd = fake_remove_cmd
try:
    p = MpvPlayer.__new__(MpvPlayer)
    p.ipc_path = 'x'
    p._running = True
    p.playlist_remove(1)
    check('mpv remove sends playlist-remove',
          ["playlist-remove", 1] in fake_remove_cmd.seen, str(fake_remove_cmd.seen))
finally:
    lp._cmd = real_cmd

# Idle mpv -> not running, never spawns.
lp._cmd = lambda ipc, cmd: {"error": "not running"}
idle = MpvPlayer.__new__(MpvPlayer)
idle.ipc_path = 'x'
idle._running = False
check('mpv remove idle -> not running',
      idle.playlist_remove(0).get('error') == 'not running')
lp._cmd = real_cmd


# --- playfiles batch: open first, append rest, never pre-clear --------------
class FakeBatchPlayer:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def play_file(self, path):
        self.calls.append(('play_file', path))
        return {'result': 'OK'} if self.error is None else {'error': self.error}

    def playlist_clear(self):
        self.calls.append(('clear',))
        return {'result': 'OK'}

    def playlist_append(self, path):
        self.calls.append(('append', path))
        return {'result': 'OK'}


fp = FakeBatchPlayer()
with contextlib.redirect_stdout(io.StringIO()):
    ok = _play_files(fp, ['a', 'b', 'c'])
check('playfiles opens the first file', ('play_file', 'a') in fp.calls, str(fp.calls))
check('playfiles appends the rest in order',
      [c for c in fp.calls if c[0] == 'append'] == [('append', 'b'), ('append', 'c')],
      str(fp.calls))
check('playfiles does not pre-clear the queue',
      ('clear',) not in fp.calls, str(fp.calls))
check('playfiles reports success', ok is True)

fp2 = FakeBatchPlayer(error='boom')
with contextlib.redirect_stdout(io.StringIO()):
    ok2 = _play_files(fp2, ['a', 'b'])
check('playfiles stops on a playback error', ok2 is False)
check('playfiles does not append after an error',
      [c for c in fp2.calls if c[0] == 'append'] == [], str(fp2.calls))


# --- remove: resolve a path to a queue index --------------------------------
class FakeQueuePlayer:
    def __init__(self):
        self.removed = []
        self.items = [
            {'index': 0, 'title': 'a.mp3', 'path': '/m/a.mp3', 'current': False},
            {'index': 1, 'title': 'b.mp3', 'path': '/m/sub/b.mp3', 'current': True},
        ]

    def playlist_items(self):
        return self.items

    def playlist_remove(self, index):
        self.removed.append(index)
        return {'result': 'OK'}


qp = FakeQueuePlayer()
with contextlib.redirect_stdout(io.StringIO()):
    ok = _remove_from_queue(qp, '/m/sub/b.mp3')
check('remove matches full path', ok is True and qp.removed == [1], str(qp.removed))

qp = FakeQueuePlayer()
with contextlib.redirect_stdout(io.StringIO()):
    ok = _remove_from_queue(qp, 'a.mp3')
check('remove falls back to basename', ok is True and qp.removed == [0], str(qp.removed))

qp = FakeQueuePlayer()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ok = _remove_from_queue(qp, 'zzz.mp3')
check('remove reports a path not in queue', ok is False and qp.removed == [])
check('remove prints not-in-queue message', 'Not in queue: zzz.mp3' in buf.getvalue(),
      repr(buf.getvalue()))

# --- remove by list index ---------------------------------------------------
qp = FakeQueuePlayer()
with contextlib.redirect_stdout(io.StringIO()):
    ok = _remove_from_queue(qp, '2')
check('remove by 1-based list index', ok is True and qp.removed == [1], str(qp.removed))

qp = FakeQueuePlayer()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ok = _remove_from_queue(qp, '99')
check('remove rejects an out-of-range index', ok is False and qp.removed == [])
check('remove prints out-of-range message', 'No queue entry: 99' in buf.getvalue(),
      repr(buf.getvalue()))


# --- remove: number-like filenames beat the index fallback -------------------
class FakeNumericQueue(FakeQueuePlayer):
    def __init__(self):
        super().__init__()
        self.items = [
            {'index': 0, 'title': '7', 'path': '/m/7', 'current': False},
            {'index': 1, 'title': 'other', 'path': '/m/other', 'current': True},
        ]


qp = FakeNumericQueue()
with contextlib.redirect_stdout(io.StringIO()):
    ok = _remove_from_queue(qp, '7')
check('number-like filename matches by title before index', ok is True and qp.removed == [0],
      str(qp.removed))


# --- CLI formatting ---------------------------------------------------------
def render(entries, as_json=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_playlist(entries, json_output=as_json)
    return buf.getvalue()


sample = [
    {'index': 0, 'title': 'a.mp3', 'path': '/m/a.mp3', 'current': False},
    {'index': 1, 'title': 'b.mp3', 'path': '/m/b.mp3', 'current': True},
]
out = render(sample)
check('print marks current entry', '▶ 2. b.mp3' in out, repr(out))
check('print numbers all entries', '  1. a.mp3' in out, repr(out))
check('print appends the source path',
      '  1. a.mp3  —  /m/a.mp3' in out and '▶ 2. b.mp3  —  /m/b.mp3' in out, repr(out))
check('empty queue message', render([]).strip() == 'Queue is empty.')

no_path = [{'index': 0, 'title': 'x', 'path': '', 'current': False}]
check('print omits the path suffix when empty', render(no_path).strip() == '1. x',
      repr(render(no_path)))

js = render(sample, as_json=True)
check('json output round-trips', json.loads(js) == sample, js)


# --- action ordering: file/queue actions grouped before control -------------
check('action list has append/list/remove',
      all(a in ACTION_CHOICES for a in ('append', 'list', 'remove')),
      str(ACTION_CHOICES))
check('old action names removed',
      'enqueue' not in ACTION_CHOICES and 'playlist' not in ACTION_CHOICES,
      str(ACTION_CHOICES))
check('status stays last',
      ACTION_CHOICES.index('status') == len(ACTION_CHOICES) - 1, str(ACTION_CHOICES))
check('EPILOG groups file/queue actions on one line',
      'files    playfile | playfiles | append | list | remove' in EPILOG, EPILOG)
check('EPILOG files group precedes control',
      EPILOG.index('files    playfile') < EPILOG.index('control  pause'), EPILOG)
check('EPILOG does not mention old names',
      'enqueue' not in EPILOG and 'playlist' not in EPILOG, EPILOG)

print()
print('TOTAL: %d passed, %d failed' % (passed, failed))
sys.exit(0 if failed == 0 else 1)
