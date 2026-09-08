#!/usr/bin/env python3
"""
Control playback (pause, resume, skip, volume) for KODI or local mpv.
"""

import argparse
import json
import sys
import os

from aiplayer.kodi_api import KodiAPI
from aiplayer.player import Player, PlayerMode


def control_playback(player, action):
    """Control playback via Player abstraction or KodiAPI directly."""
    if isinstance(player, Player):
        return player.control_playback(action)

    # Fallback: direct KodiAPI
    player_id = _get_active_player(player)
    if player_id is None:
        return False

    actions = {
        'pause': None,
        'play': None,
        'playpause': None,
        'next': 'next',
        'prev': 'previous',
        'restart': None,
    }

    labels = {'pause': 'Play/Pause', 'play': 'Play/Pause', 'playpause': 'Play/Pause',
              'next': 'Next', 'prev': 'Prev', 'restart': 'Restart'}
    label = labels.get(action, action)

    if action in ('pause', 'play', 'playpause'):
        result = player.player_play_pause(player_id)
        ok = result.get('result') == 'OK'
        print(f"{label}: {'OK' if ok else 'failed'}")
        return ok
    elif action in ('next', 'prev'):
        to = actions[action]
        result = player.player_go_to(player_id, to)
        ok = result.get('result') == 'OK'
        print(f"{label}: {'OK' if ok else 'failed'}")
        return ok
    elif action == 'restart':
        result = player.player_seek(player_id, 'beginning')
        ok = result.get('result') == 'OK'
        print(f"{label}: {'OK' if ok else 'failed'}")
        return ok
    else:
        print(f"Unknown action: {action}")
        return False


def control_volume(player, action):
    """Control volume via Player abstraction or KodiAPI directly."""
    if isinstance(player, Player):
        return player.control_volume(action)

    # Fallback: direct KodiAPI
    response = player.application_get_properties()
    if not response or 'result' not in response:
        print("Cannot get volume.")
        return False

    current_volume = response['result'].get('volume', 50)
    print(f"Current volume: {current_volume}%")

    if action == 'volume_up':
        new_volume = min(100, current_volume + 10)
    elif action == 'volume_down':
        new_volume = max(0, current_volume - 10)
    elif action == 'mute':
        new_volume = 0
    else:
        print(f"Unknown volume action: {action}")
        return False

    result = player.application_set_volume(new_volume)
    print(f"Volume set to {new_volume}%: {json.dumps(result, indent=2)}")
    return result.get('result') == 'OK'


def _get_active_player(api):
    response = api.player_get_active_players()
    if not response or 'result' not in response:
        print("No active player found.")
        return None
    players = response['result']
    if not players:
        print("No active player found.")
        return None
    return players[0].get('playerid', 0)


def main():
    parser = argparse.ArgumentParser(description='Control playback (KODI or local mpv)')
    parser.add_argument('--host', default='127.0.0.1', help='KODI host IP')
    parser.add_argument('--port', type=int, default=8080, help='KODI port')
    parser.add_argument('--username', default='', help='KODI username')
    parser.add_argument('--password', default='', help='KODI password')
    parser.add_argument('--protocol', choices=['tcp', 'http', 'auto'], default='auto', help='Connection protocol')
    parser.add_argument('--action', choices=['pause', 'play', 'playpause', 'next', 'prev',
                                              'restart', 'volume_up', 'volume_down', 'mute'],
                        required=True, help='Action to perform')
    parser.add_argument('--local', action='store_true', help='Use local mpv mode (no KODI)')

    args = parser.parse_args()

    if args.local:
        player = Player(mode=PlayerMode.LOCAL)
        print("Using local mpv player")
    else:
        api = KodiAPI(args.host, args.port, args.username, args.password, protocol=args.protocol)
        version = api.get_version()
        if not version or 'result' not in version:
            print(f"Cannot connect to KODI at {args.host}:{args.port}")
            sys.exit(1)
        print(f"Connected to KODI v{version['result'].get('version', 'unknown')}")
        player = api

    if args.action in ('pause', 'play', 'playpause', 'next', 'prev', 'restart'):
        success = control_playback(player, args.action)
    elif args.action in ('volume_up', 'volume_down', 'mute'):
        success = control_volume(player, args.action)
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
