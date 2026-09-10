#!/usr/bin/env python3
"""
Player abstraction layer - unified interface for KODI and local mpv playback.
"""

from aiplayer.kodi_api import KodiAPI
from aiplayer.local_player import MpvPlayer


class PlayerMode:
    KODI = "kodi"
    LOCAL = "local"


def resolve_kodi_api(player):
    """Extract KodiAPI from a Player instance; player itself if already
    a KodiAPI; None otherwise."""
    if player is None:
        return None
    if isinstance(player, KodiAPI):
        return player
    if hasattr(player, 'kodi') and player.kodi:
        return player.kodi
    return None


def is_local_player(player):
    """True when player is a local (mpv) Player instance."""
    return player is not None and getattr(player, 'mode', None) == PlayerMode.LOCAL


class Player:
    def __init__(self, mode, kodi_config=None, local_config=None):
        self.mode = mode
        self.kodi = None
        self.local = None

        if mode == PlayerMode.KODI and kodi_config:
            self.kodi = KodiAPI(
                host=kodi_config.get('host', '127.0.0.1'),
                port=kodi_config.get('port'),
                username=kodi_config.get('username', ''),
                password=kodi_config.get('password', ''),
                protocol=kodi_config.get('protocol', 'auto'),
            )
        elif mode == PlayerMode.LOCAL:
            mpv_path = (local_config or {}).get('mpv_path')
            self.local = MpvPlayer(mpv_path=mpv_path)

    def play_file(self, path):
        if self.kodi:
            return self.kodi.player_open_item({'file': path})
        elif self.local:
            return self.local.play(path)

    def play_url(self, url):
        if self.kodi:
            return self.kodi.player_open_item({'file': url})
        elif self.local:
            return self.local.play(url)

    def play_item(self, item):
        if self.kodi:
            return self.kodi.player_open_item(item)
        elif self.local:
            f = item.get('file') or item.get('path', '')
            return self.local.play(f)

    def control_playback(self, action):
        if self.kodi:
            return self._kodi_playback(action)
        elif self.local:
            return self._local_playback(action)

    def control_volume(self, action):
        if self.kodi:
            return self._kodi_volume(action)
        elif self.local:
            return self._local_volume(action)

    def current_file(self):
        """Get currently playing filename (single IPC call)."""
        if self.kodi:
            player_id = self.get_active_player()
            if player_id is None:
                return None
            result = self.kodi.player_get_item(player_id, ['file', 'title'])
            if result and 'result' in result:
                item = result['result'].get('item', {})
                return item.get('title') or item.get('file')
            return None
        elif self.local:
            import time
            time.sleep(0.15)
            r = self.local.get_properties(['filename'])
            return r.get('filename')
        return None

    def status(self):
        """Get current playback status."""
        if self.kodi:
            player_id = self.get_active_player()
            if player_id is None:
                return {}
            result = self.kodi.player_get_item(player_id, ['title', 'file', 'artist', 'album', 'duration'])
            props = self.kodi.player_get_properties(player_id, ['time', 'speed'])
            info = result.get('result', {}).get('item', {}) if result else {}
            if props and 'result' in props:
                info['time'] = props['result'].get('time', {})
                info['speed'] = props['result'].get('speed', 1)
            if 'duration' in info and 'time' in info:
                t = info['time']
                pos = t.get('hours', 0) * 3600 + t.get('minutes', 0) * 60 + t.get('seconds', 0)
                info['time-pos'] = pos
                info['remaining'] = info['duration'] - pos
            return info
        elif self.local:
            return self.local.status()
        return {}

    def playlist_append(self, path):
        if self.kodi:
            return self.kodi.playlist_add(0, {'file': path})
        elif self.local:
            return self.local.playlist_append(path)

    def playlist_clear(self):
        if self.kodi:
            return self.kodi.playlist_clear(0)
        elif self.local:
            return self.local.playlist_clear()

    def playlist_play_index(self, index):
        if self.kodi:
            return self.kodi.player_open_item({'playlistid': 0, 'position': index})
        elif self.local:
            return self.local.playlist_play_index(index)

    def play_next(self):
        if self.kodi and self.get_active_player():
            pid = self.get_active_player()
            return self.kodi.player_go_to(pid, 'next')
        elif self.local:
            return self.local.play_next()

    def get_active_player(self):
        if self.kodi:
            response = self.kodi.player_get_active_players()
            if response and 'result' in response:
                players = response['result']
                if players:
                    return players[0].get('playerid', 0)
        return None

    def _kodi_playback(self, action):
        player_id = self.get_active_player()
        if player_id is None:
            print("No active player.")
            return False

        if action in ('pause', 'play', 'playpause'):
            label, call = 'Play/Pause', lambda: self.kodi.player_play_pause(player_id)
        elif action == 'next':
            label, call = 'Next', lambda: self.kodi.player_go_to(player_id, 'next')
        elif action == 'prev':
            label, call = 'Prev', lambda: self.kodi.player_go_to(player_id, 'previous')
        elif action == 'stop':
            label, call = 'Stop', lambda: self.kodi.player_stop(player_id)
        elif action == 'restart':
            label, call = 'Restart', lambda: self.kodi.player_seek(player_id, 'beginning')
        else:
            return False

        result = call()
        ok = result.get('result') == 'OK'
        print(f"{label}: {'OK' if ok else 'failed'}")
        if ok and action != 'stop':
            title = self.current_file()
            if title:
                print(f"  Now: {title}")
        return ok

    def _local_playback(self, action):
        labels = {'pause': 'Pause', 'play': 'Play', 'playpause': 'Play/Pause',
                  'next': 'Next', 'prev': 'Prev',
                  'stop': 'Stop', 'restart': 'Restart'}
        label = labels.get(action, action)

        calls = {
            'pause': lambda: self.local.set_pause(True),
            'play': lambda: self.local.set_pause(False),
            'playpause': self.local.play_pause,
            'next': lambda: self.local.go_to('next'),
            'prev': lambda: self.local.go_to('previous'),
            'stop': self.local.stop,
            'restart': lambda: self.local.seek('beginning'),
        }
        if action not in calls:
            return False
        r = calls[action]()
        if isinstance(r, dict) and r.get('error') == 'not running':
            print("Nothing playing.")
            return True
        ok = r.get('error') in (None, 'success')
        print(f"{label}: {'OK' if ok else 'failed - ' + str(r.get('error', 'unknown'))}")
        if ok and action != 'stop':
            title = self.current_file()
            if title:
                print(f"  Now: {title}")
        return ok

    def _kodi_volume(self, action):
        response = self.kodi.application_get_properties()
        if not response or 'result' not in response:
            print("Volume: failed - cannot get volume")
            return False
        current = response['result'].get('volume', 50)

        if action == 'volume_up':
            new_vol = min(100, current + 10)
        elif action == 'volume_down':
            new_vol = max(0, current - 10)
        elif action == 'mute':
            new_vol = 0
        else:
            return False

        result = self.kodi.application_set_volume(new_vol)
        ok = result.get('result') == 'OK'
        print(f"Volume: {new_vol}% {'OK' if ok else 'failed'}")
        return ok

    def _local_volume(self, action):
        labels = {'volume_up': 'Volume up', 'volume_down': 'Volume down', 'mute': 'Mute'}
        label = labels.get(action, action)

        if action == 'volume_up':
            r = self.local.volume_up()
        elif action == 'volume_down':
            r = self.local.volume_down()
        elif action == 'mute':
            r = self.local.set_volume(0)
        else:
            return False

        if isinstance(r, dict) and r.get('error') == 'not running':
            print("Nothing playing.")
            return True
        ok = r.get('error') in (None, 'success')
        print(f"{label}: {'OK' if ok else 'failed - ' + str(r.get('error', 'unknown'))}")
        return ok

