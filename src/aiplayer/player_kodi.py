#!/usr/bin/env python3
"""KODI backend: adapts KodiAPI to the Player interface."""

import os

from aiplayer.kodi_api import KodiAPI
from aiplayer.player import Player, PlayerMode


class KodiBackend(Player):
    # Active playlist id (0=audio, 1=video), resolved lazily for append/clear/
    # jump so write operations and playlist_items() agree on the same list.
    _playlist_id = None

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
        result = self.kodi.player_open_item({'file': path})
        self._playlist_id = None
        return result

    def play_url(self, url):
        result = self.kodi.player_open_item({'file': url})
        self._playlist_id = None
        return result

    def play_item(self, item):
        result = self.kodi.player_open_item(item)
        self._playlist_id = None
        return result

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
        return self.kodi.playlist_add(self._playlist_id_for_write(), {'file': path})

    def playlist_clear(self):
        return self.kodi.playlist_clear(self._playlist_id_for_write())

    def playlist_remove(self, index):
        return self.kodi.playlist_remove(self._playlist_id_for_write(), index)

    def playlist_play_index(self, index):
        return self.kodi.player_open_item(
            {'playlistid': self._playlist_id_for_write(), 'position': index})

    def play_next(self):
        if self.get_active_player():
            pid = self.get_active_player()
            return self.kodi.player_go_to(pid, 'next')

    def _active_playlist(self):
        """Return (playlist_id, position) for the active player.

        playlist_id is 0=audio / 1=video (2=picture): taken from
        Player.GetProperties when the box reports it, else inferred from the
        player type. position is the current playlist index, or None when
        nothing is playing.
        """
        playlist_id, position = 0, None
        active = self.kodi.player_get_active_players()
        players = active.get('result') if active else None
        if players:
            player_id = players[0].get('playerid', 0)
            props = self.kodi.player_get_properties(player_id, ['position', 'playlistid'])
            result = props.get('result') if props and 'result' in props else None
            if result is None:
                props = self.kodi.player_get_properties(player_id, ['position'])
                result = props.get('result') if props and 'result' in props else {}
            if result.get('playlistid') is not None:
                playlist_id = result['playlistid']
            elif players[0].get('type') == 'video':
                playlist_id = 1
            if result.get('position') is not None:
                position = result['position']
        return playlist_id, position

    def _playlist_id_for_write(self):
        """Playlist id for append/clear/jump, resolved once and cached until
        the next play request (the media type cannot change in between)."""
        if self._playlist_id is None:
            self._playlist_id, _ = self._active_playlist()
        return self._playlist_id

    def playlist_items(self):
        """Return the active playlist (audio=0 / video=1) as entry dicts."""
        playlist_id, position = self._active_playlist()

        response = self.kodi.playlist_get_items(playlist_id, ['title', 'file'])
        if not response or 'result' not in response:
            return []
        items = response['result'].get('items', [])
        entries = []
        for i, item in enumerate(items):
            path = item.get('file') or ''
            entries.append({
                'index': i,
                'title': item.get('title') or item.get('label')
                         or os.path.basename(path) or path or '?',
                'path': path,
                'current': position == i,
            })
        return entries

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
            # Player.PlayPause is a blind toggle: "play" on a playing player
            # pauses it, "pause" on a paused one resumes. Check speed first so
            # play/pause are state-aware; playpause stays an explicit toggle.
            if action in ('play', 'pause'):
                props = self.kodi.player_get_properties(player_id, ['speed'])
                speed = props.get('result', {}).get('speed') if props and 'result' in props else None
                if action == 'play' and speed not in (None, 0):
                    print("Play: already playing")
                    return True
                if action == 'pause' and speed == 0:
                    print("Pause: already paused")
                    return True
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