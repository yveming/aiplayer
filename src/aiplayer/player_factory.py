#!/usr/bin/env python3
"""Factory assembling Player backends from a mode and configuration."""

from aiplayer.player import PlayerMode
from aiplayer.player_kodi import KodiBackend
from aiplayer.player_mpv import MpvBackend


def create_player(mode, kodi_config=None, local_config=None):
    """Build the Player backend for the requested mode."""
    if mode == PlayerMode.KODI:
        return KodiBackend(kodi_config)
    if mode == PlayerMode.LOCAL:
        mpv_path = (local_config or {}).get('mpv_path')
        return MpvBackend(mpv_path=mpv_path)
    raise ValueError(f"Unknown player mode: {mode!r}")