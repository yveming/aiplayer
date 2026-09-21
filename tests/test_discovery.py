#!/usr/bin/env python3
"""Discovery checks (offline): sentinel --host, raw-socket TCP probe,
credential passing, and multi-instance selection.

No real network / KODI needed.
"""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import aiplayer.discover_kodi as dk
from aiplayer.aiplayer import _player_kind, _select_instance

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS %s' % name)
    else:
        failed += 1
        print('  FAIL %s %s' % (name, detail))


# --- _player_kind: an explicit --host is None unless the user passed it -----
check('auto without host -> auto',
      _player_kind(argparse.Namespace(local=False, host=None, auto=True)) == 'auto')
check('explicit host -> kodi (auto ignored)',
      _player_kind(argparse.Namespace(local=False, host='1.2.3.4', auto=True)) == 'kodi')
check('local wins over host and auto',
      _player_kind(argparse.Namespace(local=True, host='1.2.3.4', auto=True)) == 'local')
check('no flags -> local',
      _player_kind(argparse.Namespace(local=False, host=None, auto=False)) == 'local')
check('explicit host -> kodi',
      _player_kind(argparse.Namespace(local=False, host='1.2.3.4', auto=False)) == 'kodi')


# --- _select_instance: never silently pick [0] when ambiguous --------------
a = [{'ip': '1.1.1.1', 'name': 'Alpha', 'port': 9090, 'protocol': 'tcp'},
     {'ip': '2.2.2.2', 'name': 'Beta', 'port': 8080, 'protocol': 'http'}]
check('single instance passes through', _select_instance([a[0]], 'x') == a[0])
check('match by ip', _select_instance(a, '2.2.2.2') == a[1])
check('match by name is case-insensitive', _select_instance(a, 'alpha') == a[0])
check('no match -> None', _select_instance(a, '9.9.9.9') is None)
check('no preferred host with many -> None', _select_instance(a, '') is None)
check('empty list -> None', _select_instance([], 'x') is None)


# --- raw-socket TCP probe (the transport kodi_api actually uses) -----------
class FakeSock:
    def __init__(self, response=None, raise_on_connect=False):
        self.response = response
        self.raise_on_connect = raise_on_connect
        self.closed = False

    def settimeout(self, t):
        pass

    def connect(self, addr):
        if self.raise_on_connect:
            raise OSError('refused')

    def sendall(self, data):
        pass

    def recv(self, n):
        return self.response

    def close(self):
        self.closed = True


real_socket = dk.socket.socket
try:
    dk.socket.socket = lambda *a, **k: FakeSock(
        json.dumps({'id': 1, 'result': {'version': {'major': 13}}}).encode())
    check('tcp probe accepts a version reply', dk.check_kodi_api_tcp('1.2.3.4', 9090) is True)

    dk.socket.socket = lambda *a, **k: FakeSock(b'{"id":1,"error":{"code":-1}}\n')
    check('tcp probe rejects a non-version reply', dk.check_kodi_api_tcp('1.2.3.4', 9090) is False)

    dk.socket.socket = lambda *a, **k: FakeSock(raise_on_connect=True)
    check('tcp probe returns False on connection error',
          dk.check_kodi_api_tcp('1.2.3.4', 9090) is False)
finally:
    dk.socket.socket = real_socket


# --- discover_kodi passes credentials and picks the raw TCP box ------------
recorded = {'creds': None, 'calls': []}


def fake_http(ip, port=8080, credentials=None):
    recorded['calls'].append(('http', ip, port, credentials))
    return False  # HTTP not available; force the TCP path


def fake_tcp(ip, port=9090, timeout=3):
    recorded['calls'].append(('tcp', ip, port))
    return ip == '10.0.0.5'


real_http, real_tcp = dk.check_kodi_api_http, dk.check_kodi_api_tcp
real_mdns, real_ssdp = dk.discover_mdns, dk.discover_ssdp
try:
    dk.check_kodi_api_http = fake_http
    dk.check_kodi_api_tcp = fake_tcp
    dk.discover_mdns = lambda timeout=3: [{'ip': '10.0.0.5', 'port': 22, 'name': 'MediaBox'}]
    dk.discover_ssdp = lambda timeout=5: []
    with contextlib.redirect_stdout(io.StringIO()):
        insts = dk.discover_kodi(credentials=[('kodi', '<pass>')])
    check('tcp-only box discovered', len(insts) == 1 and insts[0]['ip'] == '10.0.0.5',
          str(insts))
    check('discovered protocol is tcp',
          insts and insts[0].get('protocol') == 'tcp', str(insts))
    check('credentials forwarded to http probe',
          any(c[0] == 'http' and c[3] == [('kodi', '<pass>')] for c in recorded['calls']),
          str(recorded['calls']))
finally:
    dk.check_kodi_api_http = real_http
    dk.check_kodi_api_tcp = real_tcp
    dk.discover_mdns = real_mdns
    dk.discover_ssdp = real_ssdp


# --- KodiAPI protocol='auto' resolves HTTP->TCP for remote hosts -----------
from aiplayer.kodi_api import KodiAPI

api = KodiAPI('10.0.0.5', protocol='auto')
check('auto stays unresolved until first request', api._auto_resolved is False)
api._probe_version = lambda: api.protocol == 'tcp'
api._resolve_auto()
check('auto falls back to tcp when http fails',
      api.protocol == 'tcp' and api.port == 9090, f'{api.protocol}:{api.port}')

api = KodiAPI('10.0.0.6', protocol='auto')
api._probe_version = lambda: api.protocol == 'http'
api._resolve_auto()
check('auto uses http when it answers first',
      api.protocol == 'http' and api.port == 8080, f'{api.protocol}:{api.port}')

api = KodiAPI('10.0.0.7', port=9090, protocol='auto')
api._probe_version = lambda: api.protocol == 'tcp'
api._resolve_auto()
check('explicit port is kept across auto resolution',
      api.port == 9090 and api.protocol == 'tcp', f'{api.protocol}:{api.port}')


# --- _request_tcp: an open port that is not KODI must not crash ------------
import aiplayer.kodi_api as kapi

real_sock = kapi.socket.socket


class GarbageSock:
    """Open socket that replies with non-JSON then closes."""
    def __init__(self):
        self.done = False

    def settimeout(self, t):
        pass

    def connect(self, addr):
        pass

    def sendall(self, data):
        pass

    def recv(self, n):
        if self.done:
            return b''
        self.done = True
        return b'<html>not json</html>'

    def close(self):
        pass


try:
    kapi.socket.socket = lambda *a, **k: GarbageSock()
    api = KodiAPI('1.2.3.4', 9090, protocol='tcp')
    check('_request_tcp returns None on a non-JSON reply',
          api._request_tcp('{"jsonrpc":"2.0"}') is None)

    def refuse(*a, **k):
        raise OSError('connection refused')

    kapi.socket.socket = refuse
    api = KodiAPI('1.2.3.4', 9090, protocol='tcp')
    check('_request_tcp returns None when the socket cannot be created',
          api._request_tcp('{"jsonrpc":"2.0"}') is None)
finally:
    kapi.socket.socket = real_sock


# --- _discovery_only: `aiplayer discover` ------------------------------------
import aiplayer.aiplayer as ap
from aiplayer.aiplayer import _discovery_only

real_discover = ap.discover_player

FAKE_INSTANCES = [{'name': 'MediaBox', 'ip': '10.0.0.9',
                   'port': 9090, 'protocol': 'tcp'}]


def _capture_stdout(fn):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        ret = fn()
    finally:
        sys.stdout = old
    return buf.getvalue(), ret


try:
    def noisy_discover(credentials=None, prefer_local=False):
        print('Discovering KODI instances...')  # must be suppressed for --json
        return {'mode': 'kodi', 'instances': list(FAKE_INSTANCES)}

    ap.discover_player = noisy_discover
    out, insts = _capture_stdout(lambda: _discovery_only())
    check('discovery-only returns the KODI instances',
          insts == FAKE_INSTANCES, str(insts))
    check('discovery-only keeps human-readable discovery output',
          'Discovering' in out, repr(out))

    out, insts = _capture_stdout(lambda: _discovery_only(json_output=True))
    check('discovery-only --json emits the instance array',
          json.loads(out) == FAKE_INSTANCES, repr(out))
    check('discovery-only --json suppresses discovery logs',
          'Discovering' not in out, repr(out))

    ap.discover_player = lambda credentials=None, prefer_local=False: {
        'mode': None, 'instances': None}
    out, insts = _capture_stdout(lambda: _discovery_only(json_output=True))
    check('discovery-only --json emits [] when nothing found',
          json.loads(out) == [] and insts == [], repr(out))
finally:
    ap.discover_player = real_discover


# --- `aiplayer discover` action & closed `--auto`-with-no-action entry ---------
from aiplayer.aiplayer import ACTION_CHOICES

check('discover is the first action choice',
      ACTION_CHOICES[0] == 'discover', str(ACTION_CHOICES[:3]))

_subprocess_code = (
    "import sys\n"
    "sys.argv = ['aiplayer', '--auto']\n"
    "from aiplayer.aiplayer import main\n"
    "main()\n"
)
_proc = subprocess.run(
    [sys.executable, '-X', 'utf8', '-c', _subprocess_code],
    capture_output=True, text=True, encoding='utf-8', errors='replace',
    timeout=30,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8',
         'PYTHONPATH': os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')},
)
check('bare --auto (no action) prints the no-action hint',
      'No action provided' in _proc.stdout, repr(_proc.stdout))
check('bare --auto (no action) exits 1 without discovering',
      _proc.returncode == 1, 'rc=%d out=%r' % (_proc.returncode, _proc.stdout))


print()
print('TOTAL: %d passed, %d failed' % (passed, failed))
sys.exit(0 if failed == 0 else 1)
