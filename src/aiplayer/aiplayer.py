#!/usr/bin/env python3
"""
aiplayer - Unified media player.
Auto-discovers KODI or falls back to local mpv playback with HTTP m3u/EPG for TV.
"""

import argparse
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiplayer.player import Player, PlayerMode
from aiplayer.discover import discover_player


def main():
    parser = argparse.ArgumentParser(
        description='aiplayer - Unified media player (KODI + local mpv)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('action', nargs='?', default='auto',
                        choices=['auto', 'movie', 'tv', 'music', 'channel', 'catchup', 'epg',
                                 'pause', 'play', 'playpause', 'next', 'prev', 'stop',
                                 'restart', 'volume_up', 'volume_down', 'mute',
                                 'channels', 'status', 'nowplaying', 'playfile', 'enqueue', 'playfiles'],
                        help='Action to perform')
    parser.add_argument('query', nargs='*', default=[], help='Search query or file paths')

    parser.add_argument('--host', default='', help='KODI host IP')
    parser.add_argument('--port', type=int, default=None, help='KODI port')
    parser.add_argument('--username', default='', help='KODI username')
    parser.add_argument('--password', default='', help='KODI password')
    parser.add_argument('--protocol', choices=['tcp', 'http', 'auto'], default='auto')

    parser.add_argument('--artist', default='', help='Artist name (music)')
    parser.add_argument('--album', default='', help='Album name (music)')
    parser.add_argument('--song', default='', help='Song name (music)')
    parser.add_argument('--shuffle', action='store_true', help='Shuffle playback (music)')
    parser.add_argument('--json', action='store_true', help='Output search results as JSON (for AI, no interactive prompt)')

    parser.add_argument('--date', default='', help='Date for catch-up/EPG (yesterday/today/YYYY-MM-DD)')
    parser.add_argument('--time', default='', help='Time for catch-up/EPG (HH:MM)')
    parser.add_argument('--m3u', default='', help='Path to local m3u file')
    parser.add_argument('--m3u-url', default='', help='URL to IPTV m3u (HTTP)')

    parser.add_argument('--debug', action='store_true', help='Show debug output')
    parser.add_argument('--max-depth', type=int, default=4, help='Max recursion depth for directory search')
    parser.add_argument('--local', action='store_true', help='Force local mpv mode (skip KODI discovery)')
    parser.add_argument('--mpv-path', default='', help='Path to mpv executable')
    parser.add_argument('--prefer-local', action='store_true', help='Prefer local mode even if KODI available')

    args = parser.parse_args()

    # Determine player
    player = None
    local_config = {}
    if args.mpv_path:
        local_config['mpv_path'] = args.mpv_path

    if args.local:
        # --local: skip discovery, go straight to local mode
        player = Player(mode=PlayerMode.LOCAL, local_config=local_config)
        print("Mode: local mpv")
    elif args.host:
        # User specified a KODI host directly
        player = Player(
            mode=PlayerMode.KODI,
            kodi_config={
                "host": args.host,
                "port": args.port,
                "username": args.username,
                "password": args.password,
                "protocol": args.protocol,
            },
        )
        print(f"Mode: KODI ({args.host}:{args.port or 9090})")
    else:
        # Auto-discover
        discovery = discover_player(prefer_local=args.prefer_local)
        if discovery['mode'] == 'kodi':
            inst = discovery['instances'][0]
            player = Player(
                mode=PlayerMode.KODI,
                kodi_config={
                    'host': inst['ip'],
                    'port': inst['port'],
                    'username': args.username,
                    'password': args.password,
                    'protocol': inst.get('protocol', 'auto'),
                },
            )
            print(f"Mode: KODI ({inst['ip']}:{inst['port']})")
        elif discovery['mode'] == 'local':
            player = Player(mode=PlayerMode.LOCAL, local_config=local_config)
            print("Mode: local mpv (no KODI found)")
        else:
            if args.m3u_url or args.m3u:
                player = Player(mode=PlayerMode.LOCAL, local_config=local_config)
                print("Mode: local mpv (no KODI, using m3u)")
            else:
                print("No player available. Use --host to specify KODI or --m3u-url for TV.")
                sys.exit(1)

    action = args.action
    query_list = args.query
    query = ' '.join(query_list) if query_list else ''

    if action == 'auto':
        if args.m3u_url:
            action = 'channel'
        elif query:
            if args.artist or args.song or args.album:
                action = 'music'
            elif re.search(r'[Ss]\d{1,2}[Ee]\d{1,2}', query) or \
                 re.search(r'\d{1,2}\s*[xX]\s*\d{1,2}', query) or \
                 re.search(r'[季集]', query):
                action = 'tv'
            else:
                action = 'movie'
        else:
            print("No query provided. Specify a search term or action.")
            sys.exit(1)

    from aiplayer.search_play import play_movie, play_tv_episode, play_music
    from aiplayer.playback_control import control_playback, control_volume
    from aiplayer.pvr_epg import show_current_program, play_catchup, show_epg, get_all_channels

    if action == 'movie':
        success = play_movie(player, query, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'tv':
        success = play_tv_episode(player, query, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'music':
        success = play_music(player, query, args.artist, args.album, args.song,
                            args.shuffle, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'channel':
        if not query:
            if args.m3u_url:
                from aiplayer.m3u_catchup import parse_m3u as _parse_m3u
                from aiplayer.m3u_catchup import _read_text as m3u_read
                print(f"Fetching m3u: {args.m3u_url}")
                text = m3u_read(args.m3u_url)
                entries = _parse_m3u(text)
                print(f"\nFound {len(entries)} channels:")
                for i, e in enumerate(entries, 1):
                    name = e.get('label') or e.get('tvg_name') or '?'
                    print(f"{i}. {name}")
                success = True
            else:
                print("Channel name required.")
                success = False
        elif args.m3u_url:
            from aiplayer.m3u_catchup import parse_m3u as _parse_m3u, find_channel as m3u_find
            from aiplayer.m3u_catchup import _read_text as m3u_read
            print(f"Fetching m3u: {args.m3u_url}")
            text = m3u_read(args.m3u_url)
            entries = _parse_m3u(text)
            m3u_entry = m3u_find(entries, query)
            if m3u_entry and m3u_entry.get('stream_url'):
                url = m3u_entry['stream_url']
                print(f"Stream URL: {url}")
                print("Launching mpv...")
                result = player.play_url(url)
                if isinstance(result, dict) and 'error' in result:
                    print(f"Playback error: {result['error']}")
                    success = False
                else:
                    print(f"Playing: {query}")
                    success = True
            else:
                print(f"Channel '{query}' not in m3u.")
                success = False
        else:
            success = show_current_program(player, query)
    elif action == 'catchup':
        if not args.date or not args.time:
            print("--date and --time required for catch-up.")
            sys.exit(1)
        success = play_catchup(player, query, args.date, args.time,
                              m3u_path=args.m3u or None,
                              m3u_url=args.m3u_url or None)
    elif action == 'epg':
        if not query and not args.m3u_url:
            print("Channel name required for EPG (or use --m3u-url).")
            sys.exit(1)
        success = show_epg(player, query or None, args.date, args.time, m3u_url=args.m3u_url or None)
    elif action == 'playfile':
        if not query:
            print("File path required.")
            sys.exit(1)
        result = player.play_file(query)
        if isinstance(result, dict) and result.get('error') not in (None, 'success'):
            print(f"Playback error: {result['error']}")
            success = False
        else:
            print(f"Playing: {query}")
            success = True
    elif action == 'enqueue':
        if not query:
            print("File path required.")
            sys.exit(1)
        result = player.playlist_append(query)
        if isinstance(result, dict) and result.get('error') not in (None, 'success'):
            print(f"Enqueue error: {result['error']}")
            success = False
        else:
            print(f"Enqueued: {query}")
            success = True
    elif action == 'playfiles':
        if not query_list:
            print("File paths required.")
            sys.exit(1)
        player.playlist_clear()
        for path in query_list:
            player.playlist_append(path)
        player.playlist_play_index(0)
        print(f"Playing {len(query_list)} file(s)")
        success = True
    elif action == 'channels':
        if args.m3u_url:
            from aiplayer.m3u_catchup import parse_m3u as _parse_m3u, _read_text as m3u_read
            text = m3u_read(args.m3u_url)
            entries = _parse_m3u(text)
            print(f"\nFound {len(entries)} channels:")
            for i, e in enumerate(entries, 1):
                name = e.get('label') or e.get('tvg_name') or '?'
                print(f"{i}. {name}")
            success = True
        else:
            api = player.kodi if hasattr(player, 'kodi') and player.kodi else None
            if api:
                channels = get_all_channels(api)
                if channels:
                    print(f"\nFound {len(channels)} channels:")
                    for i, ch in enumerate(channels, 1):
                        print(f"{i}. {ch.get('label', 'Unknown')} (ID: {ch.get('channelid', 'N/A')})")
                    success = True
                else:
                    print("No channels found.")
                    success = False
            else:
                print("KODI required for PVR channels.")
                success = False
    elif action in ('status', 'nowplaying'):
        info = player.status()
        if not info:
            print("Nothing playing.")
        else:
            title = info.get("title") or info.get("filename") or info.get("path", "Unknown")
            artist = info.get("artist", "")
            album = info.get("album", "")
            if artist:
                title = f"{artist} - {title}"
            if album:
                title = f"{title}  [{album}]"
            pos = info.get("time-pos")
            dur = info.get("duration")
            if pos is not None and dur:
                mm, ss = divmod(int(pos), 60)
                hh, mm = divmod(mm, 60)
                pos_str = f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"
                dur_int = int(dur)
                dmm, dss = divmod(dur_int, 60)
                dhh, dmm = divmod(dmm, 60)
                dur_str = f"{dhh}:{dmm:02d}:{dss:02d}" if dhh else f"{dmm}:{dss:02d}"
                remain = dur - pos
                rmm, rss = divmod(int(remain), 60)
                rhh, rmm = divmod(rmm, 60)
                remain_str = f"{rhh}:{rmm:02d}:{rss:02d}" if rhh else f"{rmm}:{rss:02d}"
                print(f"Playing: {title}")
                print(f"  {pos_str} / {dur_str}  ({remain_str} remaining)")
            else:
                print(f"Playing: {title}")
        success = True
    elif action in ('pause', 'play', 'playpause', 'next', 'prev', 'stop', 'restart'):
        success = control_playback(player, action)
    elif action in ('volume_up', 'volume_down', 'mute'):
        success = control_volume(player, action)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

