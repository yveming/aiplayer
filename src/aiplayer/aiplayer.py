#!/usr/bin/env python3
"""
aiplayer - Unified media player.
Auto-discovers KODI or falls back to local mpv playback with HTTP m3u/EPG for TV.
"""

import argparse
import contextlib
import io
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiplayer.player import PlayerMode, resolve_kodi_api
from aiplayer.player_factory import create_player
from aiplayer.discover import discover_player
from aiplayer.config import load_config
from aiplayer.m3u_catchup import parse_m3u as _parse_m3u, find_channel as m3u_find, _read_text as m3u_read


def _load_m3u_channels(m3u_source, announce=False):
    """Fetch + parse an m3u source and print the numbered channel list.

    Returns the parsed entries.  `announce` adds the "Fetching m3u" line
    (used by the tv action when announcing a fetch).
    """
    if announce:
        print(f"Fetching m3u: {m3u_source}")
    entries = _parse_m3u(m3u_read(m3u_source))
    print(f"\nFound {len(entries)} channels:")
    for i, e in enumerate(entries, 1):
        name = e.get('label') or e.get('tvg_name') or '?'
        print(f"{i}. {name}")
    return entries


def _find_m3u_entry(m3u_source, channel):
    """Fetch an m3u source and return the matching entry (or None)."""
    print(f"Fetching m3u: {m3u_source}")
    return m3u_find(_parse_m3u(m3u_read(m3u_source)), channel)


def _m3u_for_tv(args_m3u, m3u_cfg, kodi_mode):
    """Resolve the m3u source for TV actions (channel/epg/catchup).

    Explicit --m3u always wins.  Without it, config iptv.m3u is used in
    local mode only - KODI mode ignores it so PVR actions are never
    hijacked by the config.
    """
    if args_m3u is not None:
        return args_m3u
    return None if kodi_mode else m3u_cfg


def _player_kind(args):
    """Resolve the player backend from CLI flags: 'local', 'kodi' or 'auto'.

    CLI-level --local/--auto/--host are mutually exclusive (enforced in
    main()); the priority order below stays as a defensive fallback for
    callers that bypass the parser. --local wins over --host, so a
    configured kodi.host can be overridden to inspect the local mpv queue
    (e.g. `aiplayer --local playlist`).
    """
    if getattr(args, 'local', False):
        return 'local'
    if args.host:
        return 'kodi'
    if args.auto:
        return 'auto'
    return 'local'


def _select_instance(instances, preferred_host):
    """Pick one discovered KODI instance.

    A single instance is returned as-is. With several, match the configured
    host against the discovered IP or name; return None when there is no
    unique match so the caller can list the choices instead of guessing.
    """
    if not instances:
        return None
    if len(instances) == 1:
        return instances[0]
    if preferred_host:
        wanted = preferred_host.lower()
        for inst in instances:
            if inst.get('ip', '').lower() == wanted or \
                    inst.get('name', '').lower() == wanted:
                return inst
    return None


def _discovery_only(credentials=None, json_output=False):
    """Run discovery for `aiplayer search`.

    Human mode lets discover_player() print the process and the instance
    list (falling back to local mode info). JSON mode suppresses that and
    prints just the discovered KODI instances. Returns the instance list.
    """
    if json_output:
        with contextlib.redirect_stdout(io.StringIO()):
            discovery = discover_player(credentials=credentials)
        instances = discovery.get('instances') or []
        print(json.dumps(instances, ensure_ascii=False))
        return instances
    discovery = discover_player(credentials=credentials)
    return discovery.get('instances') or []


def _epg_requires_channel(player, query, m3u):
    """True when an EPG request cannot list anything.

    A channel-less EPG works via KODI PVR or an m3u source; only error out
    when neither is available (e.g. local mpv with no --m3u/config m3u).
    """
    return not query and not m3u and resolve_kodi_api(player) is None


def _fmt_hms(seconds):
    """Format seconds as [H:]MM:SS."""
    mm, ss = divmod(int(seconds), 60)
    hh, mm = divmod(mm, 60)
    return f"{hh}:{mm:02d}:{ss:02d}" if hh else f"{mm}:{ss:02d}"


def _print_playlist(entries, json_output=False):
    """Print the current playlist, marking the playing entry."""
    if json_output:
        print(json.dumps(entries, ensure_ascii=False))
        return
    if not entries:
        print("Queue is empty.")
        return
    for e in entries:
        mark = "▶" if e.get("current") else " "
        print(f"{mark} {e['index'] + 1}. {e['title']}")


def _remove_from_queue(player, path):
    """Remove the first queue entry matching `path`.

    `list` only shows basenames, so match the full path first, then fall
    back to basename/title. Returns True on success.
    """
    entries = player.playlist_items()
    target = os.path.basename(path)
    match = next((e for e in entries if e.get('path') == path), None)
    if match is None:
        match = next((e for e in entries
                      if os.path.basename(e.get('path', '')) == target
                      or e.get('title') == path), None)
    if match is None:
        print(f"Not in queue: {path}")
        return False
    result = player.playlist_remove(match['index'])
    if isinstance(result, dict) and result.get('error') not in (None, 'success'):
        print(f"Remove error: {result['error']}")
        return False
    print(f"Removed: {match['title']}")
    return True


def _play_files(player, paths):
    """Play a batch: open the first file, then append the rest.

    Player.Open (KODI) and loadfile replace (mpv) both replace the current
    queue with the first file, so no pre-clear is needed - and clearing first
    would target the *previous* media type's KODI playlist. Appending after
    the open resolves the correct list (audio=0 / video=1).
    """
    result = player.play_file(paths[0])
    if isinstance(result, dict) and result.get("error") not in (None, "success"):
        print(f"Playback error: {result['error']}")
        return False
    for path in paths[1:]:
        player.playlist_append(path)
    print(f"Playing {len(paths)} file(s)")
    return True


ACTION_CHOICES = [
    'search', 'movie', 'video', 'tv', 'music', 'catchup', 'epg',
    'playfile', 'playfiles', 'append', 'list', 'remove',
    'pause', 'play', 'playpause', 'next', 'prev', 'stop',
    'restart', 'volume_up', 'volume_down', 'mute', 'status',
]


EPILOG = """actions:
  search   discover KODI instances (SSDP/mDNS, ~5s); --json for JSON array
  media    movie | video (TV episodes, SxxEyy) | music
  live TV  tv (play/list channels) | epg (guide) | catchup (needs --date --time)
  files    playfile | playfiles | append | list | remove
  control  pause | play | playpause | next | prev | stop | restart |
           volume_up | volume_down | mute | status

examples:
  aiplayer search                            # discover KODI instances
  aiplayer video "黑暗物质第三季第四集" --json # episodes
  aiplayer movie "阿凡达"                      # movie
  aiplayer tv "CCTV-1"                         # live TV
  aiplayer catchup "CCTV-1" --date yesterday --time 21:00"""


def main():
    cfg = load_config()
    kodi_cfg = cfg.get('kodi', {})
    iptv_cfg = cfg.get('iptv', {})
    mpv_cfg = cfg.get('mpv', {})
    parser = argparse.ArgumentParser(
        description='aiplayer - Unified media player (KODI + local mpv)',
        usage='aiplayer [flags] <action> [query] [action-flags]',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('action', nargs='?', default=None, metavar='action',
                        choices=ACTION_CHOICES,
                        help='Action to perform (required) - see "actions" below')
    parser.add_argument('query', nargs='*', default=[], metavar='query',
                        help='Search query or file paths')

    g_kodi = parser.add_argument_group('KODI connection')
    # Defaults stay None so an *explicit* --host/--auto can be told apart from
    # config values: argparse defaults derived from config made --host always
    # truthy, which permanently shadowed --auto in _player_kind().
    g_kodi.add_argument('--host', default=None,
                        help='KODI host IP/hostname (default from config)')
    g_kodi.add_argument('--port', type=int, default=None,
                        help='KODI port (default from config)')
    g_kodi.add_argument('--username', default=None,
                        help='KODI username (default from config)')
    g_kodi.add_argument('--password', default=None,
                        help='KODI password (default from config)')
    _cfg_protocol = kodi_cfg.get('protocol') or 'auto'
    g_kodi.add_argument('--protocol', choices=['tcp', 'http', 'auto'],
                        default=_cfg_protocol if _cfg_protocol in ('tcp', 'http', 'auto') else 'auto',
                        help='Connection protocol')
    g_kodi.add_argument('--auto', action='store_true',
                        help='Auto-discover KODI (SSDP/mDNS, ~5s), fall back to local mpv')

    g_iptv = parser.add_argument_group('IPTV')
    g_iptv.add_argument('--m3u', default=None,
                        help='IPTV m3u: URL or file path (default: config iptv.m3u, local mode only)')
    g_iptv.add_argument('--epg', default=None,
                        help='XMLTV EPG (priority: --epg > config iptv.epg > m3u x-tvg-url)')
    g_iptv.add_argument('--date', default='',
                        help='Date for catch-up/EPG (yesterday/today/YYYY-MM-DD)')
    g_iptv.add_argument('--time', default='', help='Time for catch-up/EPG (HH:MM)')

    g_music = parser.add_argument_group('music')
    g_music.add_argument('--artist', default='', help='Artist name filter')
    g_music.add_argument('--album', default='', help='Album name filter')
    g_music.add_argument('--song', default='', help='Song name filter')
    g_music.add_argument('--shuffle', action='store_true', help='Shuffle playback order')

    g_gen = parser.add_argument_group('general')
    g_gen.add_argument('--local', action='store_true',
                       help='Force local mpv playback (ignore config/--host KODI)')
    g_gen.add_argument('--json', action='store_true',
                       help='Search actions print JSON, never auto-play (for AI)')
    g_gen.add_argument('--debug', action='store_true', help='Show debug output')
    g_gen.add_argument('--max-depth', type=int, default=4, help='Directory recursion depth')
    g_gen.add_argument('--mpv-path', default=mpv_cfg.get('path', ''),
                       help='Path to mpv executable (default from config)')

    args = parser.parse_args()
    # Mode flags are mutually exclusive: an explicit --local/--auto/--host
    # combo is a command-line error (exit 2), not a silent priority pick.
    if sum(1 for v in (args.local, args.auto, args.host is not None) if v) > 1:
        parser.error('--local/--auto/--host are mutually exclusive (choose one)')
    # Resolve connection settings CLI > config. args.host stays untouched so
    # _player_kind() only treats an explicit --host as KODI mode.
    kodi_host = args.host if args.host is not None else kodi_cfg.get('host', '')
    # An explicit --host selects a different box; do not inherit the configured
    # port (which belongs to the configured host). Let protocol='auto' pick the
    # right default (8080/9090) instead.
    if args.port is not None:
        kodi_port = args.port
    elif args.host is not None and args.host != kodi_cfg.get('host'):
        kodi_port = None
    else:
        kodi_port = kodi_cfg.get('port') or None
    kodi_user = args.username if args.username is not None else kodi_cfg.get('username', '')
    kodi_pass = args.password if args.password is not None else kodi_cfg.get('password', '')
    kodi_creds = [(kodi_user, kodi_pass)] if (kodi_user and kodi_pass) else None

    if args.action is None:
        print("No action provided. Run 'aiplayer --help' for the action list.")
        sys.exit(1)

    if args.action == 'search':
        # `aiplayer search` only discovers and lists KODI instances.
        found = _discovery_only(kodi_creds, json_output=args.json)
        sys.exit(0 if found else 1)

    m3u_explicit = args.m3u is not None
    m3u_cfg = iptv_cfg.get('m3u', '')
    m3u_source = args.m3u if m3u_explicit else m3u_cfg
    kind = _player_kind(args)
    # KODI mode ignores config m3u unless --m3u is given explicitly (no wrong-action hijacking)
    # Default (no --host/--auto/--local) follows config: a configured
    # kodi.host means KODI, otherwise local mpv. --local always wins.
    if kind == 'local' and not args.local and kodi_cfg.get('host'):
        kind = 'kodi'
    m3u_for_tv = _m3u_for_tv(args.m3u, m3u_cfg, kind == 'kodi')

    # Determine player
    player = None
    local_config = {}
    if args.mpv_path:
        local_config['mpv_path'] = args.mpv_path

    if kind == 'kodi':
        # An explicit --host was passed
        player = create_player(
            PlayerMode.KODI,
            kodi_config={
                "host": kodi_host,
                "port": kodi_port,
                "username": kodi_user,
                "password": kodi_pass,
                "protocol": args.protocol,
            },
        )
        print(f"Mode: KODI ({kodi_host}:{kodi_port or 9090})")
    elif kind == 'auto':
        # --auto: auto-discover KODI, fall back to local
        discovery = discover_player(credentials=kodi_creds)
        if discovery['mode'] == 'kodi':
            inst = _select_instance(discovery['instances'], kodi_host)
            if inst is None:
                print("Multiple KODI instances found; pass --host to choose one:")
                for i in discovery['instances']:
                    print(f"  - {i['name']} ({i['ip']}:{i['port']})")
                sys.exit(1)
            player = create_player(
                PlayerMode.KODI,
                kodi_config={
                    'host': inst['ip'],
                    'port': inst['port'],
                    'username': kodi_user,
                    'password': kodi_pass,
                    'protocol': inst.get('protocol', 'auto'),
                },
            )
            print(f"Mode: KODI ({inst['ip']}:{inst['port']})")
        elif discovery['mode'] == 'local':
            player = create_player(PlayerMode.LOCAL, local_config=local_config)
            print("Mode: local mpv (no KODI found)")
        else:
            if m3u_source:
                player = create_player(PlayerMode.LOCAL, local_config=local_config)
                print("Mode: local mpv (no KODI, using m3u)")
            else:
                print("No player available. Use --host to specify KODI, search to discover, or --m3u (URL or file path) for TV.")
                sys.exit(1)
    else:
        # Default: local mpv playback (skip discovery)
        player = create_player(PlayerMode.LOCAL, local_config=local_config)
        print("Mode: local mpv (forced)" if args.local else "Mode: local mpv")

    action = args.action
    query_list = args.query
    query = ' '.join(query_list) if query_list else ''

    from aiplayer.search_play import play_movie, play_tv_episode, play_music
    from aiplayer.pvr_epg import show_current_program, play_catchup, show_epg, get_all_channels

    if action == 'movie':
        success = play_movie(player, query, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'video':
        success = play_tv_episode(player, query, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'music':
        success = play_music(player, query, args.artist, args.album, args.song,
                            args.shuffle, debug=args.debug, max_depth=args.max_depth, json_output=args.json)
    elif action == 'tv':
        if query:
            if m3u_for_tv:
                m3u_entry = _find_m3u_entry(m3u_for_tv, query)
                if m3u_entry and m3u_entry.get('stream_url'):
                    url = m3u_entry['stream_url']
                    print(f"Stream URL: {url}")
                    print("Launching mpv...")
                    result = player.play_url(url)
                    if isinstance(result, dict) and result.get('error') not in (None, 'success'):
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
        elif m3u_for_tv:
            _load_m3u_channels(m3u_for_tv, announce=True)
            success = True
        else:
            api = resolve_kodi_api(player)
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
                print("Channel name required, or pass --m3u / set iptv.m3u in config to list channels.")
                success = False
    elif action == 'catchup':
        if not args.date or not args.time:
            print("--date and --time required for catch-up.")
            sys.exit(1)
        success = play_catchup(player, query, args.date, args.time,
                              m3u=m3u_for_tv or None,
                              epg=args.epg or None)
    elif action == 'epg':
        if _epg_requires_channel(player, query, m3u_for_tv):
            print("Channel name required for EPG (or use --m3u).")
            sys.exit(1)
        success = show_epg(player, query or None, args.date, args.time,
                           m3u=m3u_for_tv or None, epg=args.epg or None)
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
    elif action == 'append':
        if not query:
            print("File path required.")
            sys.exit(1)
        result = player.playlist_append(query)
        if isinstance(result, dict) and result.get('error') not in (None, 'success'):
            print(f"Append error: {result['error']}")
            success = False
        else:
            print(f"Appended: {query}")
            success = True
    elif action == 'playfiles':
        if not query_list:
            print("File paths required.")
            sys.exit(1)
        success = _play_files(player, query_list)
    elif action == 'list':
        _print_playlist(player.playlist_items(), json_output=args.json)
        success = True
    elif action == 'remove':
        if not query:
            print("File path required.")
            sys.exit(1)
        success = _remove_from_queue(player, query)
    elif action == 'status':
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
            # Local mpv exposes `pause` directly; KODI exposes speed (0 = paused).
            paused = info.get("pause") is True or info.get("speed") == 0
            state = "Paused" if paused else "Playing"
            pos = info.get("time-pos")
            dur = info.get("duration")
            if pos is not None and dur:
                pos_str = _fmt_hms(pos)
                dur_str = _fmt_hms(dur)
                remain_str = _fmt_hms(dur - pos)
                print(f"{state}: {title}")
                print(f"  {pos_str} / {dur_str}  ({remain_str} remaining)")
            else:
                print(f"{state}: {title}")
        success = True
    elif action in ('pause', 'play', 'playpause', 'next', 'prev', 'stop', 'restart'):
        success = player.control_playback(action)
    elif action in ('volume_up', 'volume_down', 'mute'):
        success = player.control_volume(action)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

