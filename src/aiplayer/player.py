#!/usr/bin/env python3
"""
Player abstraction layer - unified interface for KODI and local mpv playback.

This module contains only the abstraction: the PlayerMode constants, the
Player abstract base class, and helpers that operate on any Player without
knowing which concrete backend is behind it. Concrete backends live in
player_kodi.py / player_mpv.py and are assembled by player_factory.py.
"""

from abc import ABC, abstractmethod


class PlayerMode:
    KODI = "kodi"
    LOCAL = "local"


class Player(ABC):
    """Unified playback interface implemented by every backend."""

    def __init__(self, mode):
        self.mode = mode

    @abstractmethod
    def play_file(self, path):
        """Play a local file path."""

    @abstractmethod
    def play_url(self, url):
        """Play a stream URL."""

    @abstractmethod
    def play_item(self, item):
        """Play a KODI-style item dict (file/path/playlistid...)."""

    @abstractmethod
    def control_playback(self, action):
        """Handle pause/play/playpause/next/prev/stop/restart."""

    @abstractmethod
    def control_volume(self, action):
        """Handle volume_up/volume_down/mute."""

    @abstractmethod
    def current_file(self):
        """Return the currently playing filename/title, or None."""

    @abstractmethod
    def status(self):
        """Return a dict describing current playback status."""

    @abstractmethod
    def playlist_append(self, path):
        """Append a path to the playlist."""

    @abstractmethod
    def playlist_clear(self):
        """Clear the playlist."""

    @abstractmethod
    def playlist_play_index(self, index):
        """Jump to a playlist index."""

    @abstractmethod
    def play_next(self):
        """Advance to the next playlist entry."""

    @abstractmethod
    def get_kodi_api(self):
        """Return the underlying KodiAPI, or None for non-KODI backends."""


def resolve_kodi_api(player):
    """Extract a KodiAPI from a Player (or return a raw KodiAPI as-is).

    Accepts a Player backend, a bare KodiAPI (or duck-typed equivalent), or
    None. Returns the KodiAPI object or None when unavailable.
    """
    if player is None:
        return None
    getter = getattr(player, 'get_kodi_api', None)
    if callable(getter):
        return getter()
    if getattr(player, 'kodi', None):
        return player.kodi
    # Bare KodiAPI / test doubles expose the JSON-RPC methods directly.
    if hasattr(player, 'player_open_item'):
        return player
    return None


def is_local_player(player):
    """True when player is a local (mpv) Player instance."""
    return player is not None and getattr(player, 'mode', None) == PlayerMode.LOCAL