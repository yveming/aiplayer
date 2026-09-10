#!/usr/bin/env python3
"""KODI backend: adapts KodiAPI to the Player interface."""

from aiplayer.kodi_api import KodiAPI
from aiplayer.player import Player, PlayerMode


class KodiBackend(Player):
    def __init__(self, kodi_config):
        super().__init__(PlayerMode.KODI)
        kodi_config = kodi_config or {}
        self.kodi = KodiAPI(
            host=kodi_config.get('host', '127.0.0.1'),
            port=kodi_config.get('port'),
            username=kodi_config.get('username', ''),
            password=kodi_config.get('password', ''),
            protocol=kodi_config.get('protocol', 'auto'),
        )

    def play_file(self, path):
        return self.kodi.player_open_item({'file': path})

    def play_url(self, url):
        return self.kodi.player_open_item({'file': url})

    def play_item(self, item):
        return self.kodi.player_open_item(item)

    def control_playback(self, action):
        return self._kodi_playback(action)

    def control_volume(self, action):
        return self._kodi_volume(action)

    def current_file(self):
        """Get currently playing filename (single IPC call)."""
        player_id = self.get_active_player()
        if player_id is None:
            return None
        result = self.kodi.player_get_item(player_id, ['file', 'title'])
        if result and 'result' in result:
            item = result['result'].get('item', {})
            return item.get('title') or item.get('file')
        return None

    def status(self):
        """Get current playback status."""
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

    def playlist_append(self, path):
        return self.kodi.playlist_add(0, {'file': path})

    def playlist_clear(self):
        return self.kodi.playlist_clear(0)

    def playlist_play_index(self, index):
        return self.kodi.player_open_item({'playlistid': 0, 'position': index})

    def play_next(self):
        if self.get_active_player():
            pid = self.get_active_player()
            return self.kodi.player_go_to(pid, 'next')

    def get_active_player(self):
        response = self.kodi.player_get_active_players()
        if response and 'result' in response:
            players = response['result']
            if players:
                return players[0].get('playerid', 0)
        return None

    def get_kodi_api(self):
        return self.kodi

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