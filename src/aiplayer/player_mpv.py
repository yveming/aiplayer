#!/usr/bin/env python3
"""Local mpv backend: adapts MpvPlayer to the Player interface."""

from aiplayer.local_player import MpvPlayer
from aiplayer.player import Player, PlayerMode


class MpvBackend(Player):
    def __init__(self, mpv_path=None):
        super().__init__(PlayerMode.LOCAL)
        self.local = MpvPlayer(mpv_path=mpv_path)

    def play_file(self, path):
        return self.local.play(path)

    def play_url(self, url):
        return self.local.play(url)

    def play_item(self, item):
        f = item.get('file') or item.get('path', '')
        return self.local.play(f)

    def control_playback(self, action):
        return self._local_playback(action)

    def control_volume(self, action):
        return self._local_volume(action)

    def current_file(self):
        """Get currently playing filename (single IPC call)."""
        import time
        time.sleep(0.15)
        r = self.local.get_properties(['filename'])
        return r.get('filename')

    def status(self):
        return self.local.status()

    def playlist_append(self, path):
        return self.local.playlist_append(path)

    def playlist_clear(self):
        return self.local.playlist_clear()

    def playlist_play_index(self, index):
        return self.local.playlist_play_index(index)

    def play_next(self):
        return self.local.play_next()

    def get_kodi_api(self):
        return None

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