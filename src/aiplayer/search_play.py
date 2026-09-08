#!/usr/bin/env python3
"""
Search and play movies, TV shows, music from KODI or local directories.
Supports Player abstraction for KODI and local mpv modes.
"""

import argparse
import json
import re
import sys
import os
import random
from difflib import SequenceMatcher
from collections import defaultdict

from aiplayer.kodi_api import KodiAPI
from aiplayer.player import Player, PlayerMode
from aiplayer import local_search

VIDEO_EXTENSIONS = local_search.VIDEO_EXTENSIONS
AUDIO_EXTENSIONS = local_search.AUDIO_EXTENSIONS
CHINESE_NUMERALS = local_search.CHINESE_NUMERALS

_chinese_to_int = local_search._chinese_to_int
parse_tv_query = local_search.parse_tv_query
extract_sXXeYY = local_search.extract_sXXeYY
extract_movie_ordinal = local_search.extract_movie_ordinal
strip_movie_ordinal = local_search.strip_movie_ordinal
extract_movie_year = local_search.extract_movie_year
fuzzy_match = local_search.fuzzy_match

_CHINESE_PATH_PARTICLES = local_search._CHINESE_PATH_PARTICLES
_PATH_PUNCTUATION = local_search._PATH_PUNCTUATION
_strip_path_particles = local_search._strip_path_particles
_normalize_for_match = local_search._normalize_for_match


def get_all_sources(api, media='files'):
    response = api.files_get_sources(media)
    if not response or 'result' not in response:
        return []
    return response['result'].get('sources', [])


KODI_SOURCE_MEDIA = {
    'music': 'music',
    'movie': 'video',
    'video': 'video',
}


def get_sources_for_media(api, media_type='video', debug=False):
    if media_type == 'music':
        allowed_endings = ('/music/',)
    elif media_type == 'movie':
        allowed_endings = ('/movie/',)
    elif media_type == 'video':
        allowed_endings = ('/video/',)
    else:
        allowed_endings = ('/movie/', '/video/', '/music/')

    VIRTUAL_PREFIXES = ('addons://', 'library://', 'videodb://', 'musicdb://')

    sources_map = {}
    kodi_media = KODI_SOURCE_MEDIA.get(media_type, media_type)
    raw_sources = get_all_sources(api, kodi_media)
    if debug:
        print(f"    [debug] KODI 'Files.GetSources({kodi_media!r})' "
              f"returned {len(raw_sources)} raw source(s); "
              f"path filter requires ending in {allowed_endings!r}")
        for s in raw_sources:
            p = s.get('file', '')
            virt = bool(p) and any(p.startswith(v) for v in VIRTUAL_PREFIXES)
            ends_ok = bool(p) and any(p.lower().endswith(e) for e in allowed_endings)
            if virt:
                tag = 'X'
            elif ends_ok:
                tag = '+'
            else:
                tag = '-'
            print(f"      {tag} label={s.get('label', '?')!r}  file={p!r}")
    for s in raw_sources:
        path = s.get('file', '')
        if not path or path in sources_map:
            continue
        if any(path.startswith(p) for p in VIRTUAL_PREFIXES):
            continue
        if not any(path.lower().endswith(e) for e in allowed_endings):
            continue
        sources_map[path] = s
    return list(sources_map.values())


def search_remote_directory(api, path, query, extensions=None, max_depth=4, debug=False,
                            video_mode=False, query_info=None):
    matches = []
    query_norm = _normalize_for_match(query)
    if not query_norm:
        return matches

    if video_mode and query_info:
        show_norm = _normalize_for_match(query_info.get('show') or '')
        target_sXXeYY = query_info.get('sXXeYY')
    else:
        show_norm = query_norm
        target_sXXeYY = None

    show_fallback = _strip_path_particles(query if not (video_mode and query_info)
                                          else (query_info.get('show') or '')).replace(' ', '').lower()

    if not show_norm:
        return matches

    def _search(current_path, depth=0, path_stack=None):
        if path_stack is None:
            path_stack = []
        if depth > max_depth:
            if debug:
                print(f"    [debug] Max depth {max_depth} reached at {current_path}")
            return

        response = api.files_get_directory(current_path)
        if not response:
            if debug:
                print(f"    [debug] No response for {current_path}")
            return
        if 'error' in response:
            if debug:
                err = response['error']
                print(f"    [debug] Error listing {current_path}: {err.get('message', err)} (code={err.get('code', '?')})")
            return
        if 'result' not in response:
            if debug:
                print(f"    [debug] No 'result' in response for {current_path}: {response}")
            return

        files = response['result'].get('files', [])
        if debug and depth == 0:
            print(f"    [debug] {current_path}: {len(files)} entries")
            for f in files:
                print(f"      - [{f.get('filetype', '?')}] {f.get('label', '?')}")

        for f in files:
            f_path = f.get('file', '')
            f_label = f.get('label', '')
            f_type = f.get('filetype', '')

            if f_type == 'directory':
                full_stack = path_stack + [f_label or os.path.basename(f_path.rstrip('/'))]
                full_norm = _normalize_for_match(''.join(full_stack))
                full_fallback = ''.join(full_stack).replace(' ', '').lower()
                matched = show_norm in full_norm or show_fallback in full_fallback
                if matched:
                    matches.append({
                        'label': f_label or os.path.basename(f_path.rstrip('/')),
                        'display': ' / '.join(full_stack),
                        'file': f_path,
                        'type': 'directory',
                        'depth': depth,
                        'sXXeYY': extract_sXXeYY(f_label),
                    })
                _search(f_path, depth + 1, full_stack)

            elif f_type == 'file':
                if extensions and not f_path.lower().endswith(extensions):
                    continue
                title_base = f_label or os.path.basename(f_path)
                title_no_ext = os.path.splitext(title_base)[0]
                full_stack = path_stack + [title_no_ext]
                full_norm = _normalize_for_match(''.join(full_stack))
                full_fallback = _strip_path_particles(''.join(full_stack)).replace(' ', '').lower()
                if show_norm not in full_norm and show_fallback not in full_fallback:
                    continue
                matches.append({
                    'label': title_no_ext,
                    'display': ' / '.join(full_stack),
                    'file': f_path,
                    'type': 'file',
                    'depth': depth,
                    'sXXeYY': extract_sXXeYY(title_no_ext),
                })

    _search(path)

    if video_mode and target_sXXeYY:
        filtered = []
        for m in matches:
            sx = m.get('sXXeYY')
            if m['type'] == 'file':
                if sx == target_sXXeYY:
                    filtered.append(m)
            else:
                if sx is None:
                    filtered.append(m)
        matches = filtered

    matches.sort(key=lambda m: (
        0 if m['type'] == 'directory' else 1,
        len(m['display']),
        m['file'].lower(),
    ))
    return matches


def search_all_remote_sources(api, query, media_type='video', debug=False,
                              video_mode=False, query_info=None, max_depth=4):
    sources = get_sources_for_media(api, media_type)
    all_matches = []
    extensions = VIDEO_EXTENSIONS if media_type in ('movie', 'tv', 'video') else AUDIO_EXTENSIONS

    if debug:
        if video_mode and query_info:
            print(f"  [debug] Query='{query}' (parsed: show='{query_info.get('show')}', sXXeYY='{query_info.get('sXXeYY')}'), media='{media_type}', max_depth={max_depth}, found {len(sources)} source(s):")
        else:
            print(f"  [debug] Query='{query}', media='{media_type}', max_depth={max_depth}, found {len(sources)} source(s):")
        for s in sources:
            print(f"    - {s.get('label', '?')}: {s.get('file', '?')}")

    for src in sources:
        src_path = src.get('file', '')
        src_label = src.get('label', 'Unknown')
        if not src_path:
            continue
        matches = search_remote_directory(api, src_path, query, None,
                                          max_depth=max_depth,
                                          debug=debug, video_mode=video_mode,
                                          query_info=query_info)
        if debug:
            print(f"  [debug] Searched '{src_label}' ({src_path}): {len(matches)} candidate match(es)")
        for m in matches:
            if m['type'] == 'file' and extensions:
                if not m['file'].lower().endswith(extensions):
                    continue
            m['source'] = src_label
            all_matches.append(m)

    return all_matches


def _pick_ordinal_files(matches, ordinal, debug=False):
    by_dir = defaultdict(list)
    for m in matches:
        if m['type'] != 'file':
            continue
        parent = os.path.dirname(m['file'])
        by_dir[parent].append(m)

    if not by_dir:
        return matches

    picked = []
    for parent, files in by_dir.items():
        files_sorted = sorted(
            files,
            key=lambda f: (
                extract_movie_year(f.get('label', '')) is None,
                extract_movie_year(f.get('label', '')) or 0,
                f.get('label', ''),
            ),
        )
        if 0 < ordinal <= len(files_sorted):
            chosen = files_sorted[ordinal - 1]
            picked.append(chosen)
            if debug:
                y = extract_movie_year(chosen.get('label', ''))
                print(f"    [debug] ordinal {ordinal} in {parent}: picked "
                      f"{chosen['label']} (year={y})")
        else:
            if debug:
                print(f"    [debug] ordinal {ordinal} out of range for "
                      f"{parent} ({len(files_sorted)} files); keeping all")
            picked.extend(files_sorted)
    return picked


def _resolve_api(player):
    """Extract KodiAPI from a Player instance, or return player as-is if it's already a KodiAPI."""
    if player is None:
        return None
    if isinstance(player, KodiAPI):
        return player
    if hasattr(player, 'kodi') and player.kodi:
        return player.kodi
    return None


def _is_local_player(player):
    """Check if player is a local (mpv) Player instance."""
    if player is None:
        return False
    return hasattr(player, 'mode') and player.mode == PlayerMode.LOCAL


def _parse_multi_selection(choice, total):
    """Parse user input: 'a'=all, 'q'=quit, '1,3,5' or '1-5' or '1 3 5'."""
    if not choice:
        return None
    choice = choice.strip().lower()
    if choice == "q":
        return None
    if choice in ("a", "all"):
        return list(range(total))
    indices = set()
    parts = re.split(r'[,\s]+', choice)
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            try:
                a, b = p.split("-", 1)
                a, b = int(a) - 1, int(b) - 1
                indices.update(range(max(0, a), min(total, b + 1)))
            except ValueError:
                continue
        else:
            try:
                i = int(p) - 1
                if 0 <= i < total:
                    indices.add(i)
                else:
                    return None
            except ValueError:
                return None
    if not indices:
        return None
    return sorted(indices)

def play_movie(player, query, debug=False, max_depth=4, json_output=False):
    """Search and play movie. player can be KodiAPI, Player, or None (auto KODI)."""
    print(f"Searching for movie: {query}")

    ordinal = extract_movie_ordinal(query)
    if ordinal is not None:
        base_query = strip_movie_ordinal(query)
        print(f"Detected series ordinal: 第{ordinal}部(search base: '{base_query}')")
    else:
        base_query = query

    api = _resolve_api(player)
    is_local = _is_local_player(player)

    if api:
        response = api.video_library_get_movies()
        if response and 'result' in response:
            movies = response['result'].get('movies', [])
            matches = fuzzy_match(query, movies)
            if matches:
                if len(matches) == 1:
                    movie = matches[0][1]
                    print(f"\nPlaying: {movie.get('title', 'Unknown')}")
                    item = {'movieid': movie['movieid']}
                    result = api.player_open_item(item)
                    print(json.dumps(result, indent=2))
                    return True
                else:
                    if json_output:
                        out = []
                        for i, (score, movie) in enumerate(matches[:50], 1):
                            entry = {"index": i, "file": movie.get('file', ''), "label": movie.get('title', 'Unknown')}
                            year = movie.get('year', '')
                            if year:
                                entry["year"] = year
                            out.append(entry)
                        print(json.dumps(out, ensure_ascii=False))
                        return True
                    print(f"\nFound {len(matches)} library matches:")
                    for i, (score, movie) in enumerate(matches[:50], 1):
                        title = movie.get('title', 'Unknown')
                        year = movie.get('year', '')
                        print(f"{i}. {title} ({year})")
                    choice = input("\nEnter number to play (or 'q' to quit): ").strip()
                    if choice.lower() == 'q':
                        return False
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(matches):
                            movie = matches[idx][1]
                            print(f"\nPlaying: {movie.get('title', 'Unknown')} ({movie.get('year', '')})")
                            item = {'movieid': movie['movieid']}
                            result = api.player_open_item(item)
                            print(json.dumps(result, indent=2))
                            return True
                    except ValueError:
                        print("Invalid choice.")
                        return False

    if api:
        print("\nNo library match. Searching remote directories...")
        remote_matches = search_all_remote_sources(api, base_query, 'movie', debug=debug, max_depth=max_depth)
    elif is_local:
        print("\nNo KODI available. Searching local directories...")
        remote_matches = local_search.search_all_local_sources(base_query, 'movie', debug=debug, max_depth=max_depth)
    else:
        print("No player available.")
        return False

    if ordinal is not None and remote_matches:
        if debug:
            print(f"  [debug] Applying ordinal filter: pick 第{ordinal}部 in each directory")
        remote_matches = _pick_ordinal_files(remote_matches, ordinal, debug=debug)

    if not remote_matches:
        print(f"No match found for '{query}'")
        return False

    if len(remote_matches) == 1:
        m = remote_matches[0]
        print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
        if player:
            player.play_file(m['file'])
        else:
            api.player_open_item({'file': m['file']})
        return True
    else:
        if json_output:
            out = []
            for i, m in enumerate(remote_matches[:50], 1):
                out.append({
                    "index": i,
                    "file": m.get('file', ''),
                    "label": m.get('label', ''),
                    "display": m.get('display', ''),
                    "type": m.get('type', ''),
                    "source": m.get('source', ''),
                })
            print(json.dumps(out, ensure_ascii=False))
            return True
        print(f"\nFound {len(remote_matches)} matches:")
        for i, m in enumerate(remote_matches[:50], 1):
            print(f"{i}. [{m['source']}] {m.get('display', m['label'])}")
        choice = input("\nEnter number to play (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            return False
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(remote_matches):
                m = remote_matches[idx]
                print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
                if player:
                    player.play_file(m['file'])
                else:
                    api.player_open_item({'file': m['file']})
                return True
        except ValueError:
            print("Invalid choice.")
            return False

    return False


def play_tv_episode(player, query, debug=False, max_depth=4, json_output=False):
    """Search and play TV episode."""
    print(f"Searching for TV episode: {query}")

    api = _resolve_api(player)
    is_local = _is_local_player(player)

    if api:
        response = api.video_library_get_episodes()
        if response and 'result' in response:
            episodes = response['result'].get('episodes', [])
            matches = fuzzy_match(query, episodes)
            if matches:
                if len(matches) == 1:
                    episode = matches[0][1]
                    show_title = episode.get('showtitle', 'Unknown')
                    title = episode.get('title', 'Unknown')
                    season = episode.get('season', 0)
                    episode_num = episode.get('episode', 0)
                    print(f"\nPlaying: {show_title} - S{season:02d}E{episode_num:02d}: {title}")
                    item = {'episodeid': episode['episodeid']}
                    result = api.player_open_item(item)
                    print(json.dumps(result, indent=2))
                    return True
                else:
                    if json_output:
                        out = []
                        for i, (score, episode) in enumerate(matches[:50], 1):
                            out.append({
                                "index": i,
                                "file": episode.get('file', ''),
                                "label": f"{episode.get('showtitle', 'Unknown')} - S{episode.get('season', 0):02d}E{episode.get('episode', 0):02d}: {episode.get('title', 'Unknown')}",
                                "showtitle": episode.get('showtitle', 'Unknown'),
                                "season": episode.get('season', 0),
                                "episode": episode.get('episode', 0),
                            })
                        print(json.dumps(out, ensure_ascii=False))
                        return True
                    print(f"\nFound {len(matches)} library matches:")
                    for i, (score, episode) in enumerate(matches[:50], 1):
                        show_title = episode.get('showtitle', 'Unknown')
                        title = episode.get('title', 'Unknown')
                        season = episode.get('season', 0)
                        episode_num = episode.get('episode', 0)
                        print(f"{i}. {show_title} - S{season:02d}E{episode_num:02d}: {title}")
                    choice = input("\nEnter number to play (or 'q' to quit): ").strip()
                    if choice.lower() == 'q':
                        return False
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(matches):
                            episode = matches[idx][1]
                            show_title = episode.get('showtitle', 'Unknown')
                            title = episode.get('title', 'Unknown')
                            season = episode.get('season', 0)
                            episode_num = episode.get('episode', 0)
                            print(f"\nPlaying: {show_title} - S{season:02d}E{episode_num:02d}: {title}")
                            item = {'episodeid': episode['episodeid']}
                            result = api.player_open_item(item)
                            print(json.dumps(result, indent=2))
                            return True
                    except ValueError:
                        print("Invalid choice.")
                        return False

    print("\nNo library match. Searching directories...")
    query_info = parse_tv_query(query)

    if api:
        remote_matches = search_all_remote_sources(api, query, 'video', debug=debug,
                                                    max_depth=max_depth, video_mode=True, query_info=query_info)
    elif is_local:
        remote_matches = local_search.search_all_local_sources(query, 'video', debug=debug,
                                                                max_depth=max_depth, video_mode=True, query_info=query_info)
    else:
        print("No player available.")
        return False

    if not remote_matches:
        print(f"No match found for '{query}'")
        return False

    if len(remote_matches) == 1:
        m = remote_matches[0]
        print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
        if player:
            player.play_file(m['file'])
        else:
            api.player_open_item({'file': m['file']})
        return True
    else:
        if json_output:
            out = []
            for i, m in enumerate(remote_matches[:50], 1):
                out.append({
                    "index": i,
                    "file": m.get('file', ''),
                    "label": m.get('label', ''),
                    "display": m.get('display', ''),
                    "type": m.get('type', ''),
                    "source": m.get('source', ''),
                })
            print(json.dumps(out, ensure_ascii=False))
            return True
        print(f"\nFound {len(remote_matches)} matches:")
        for i, m in enumerate(remote_matches[:50], 1):
            print(f"{i}. [{m['source']}] {m.get('display', m['label'])}")
        choice = input("\nEnter number to play (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            return False
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(remote_matches):
                m = remote_matches[idx]
                print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
                if player:
                    player.play_file(m['file'])
                else:
                    api.player_open_item({'file': m['file']})
                return True
        except ValueError:
            print("Invalid choice.")
            return False

    return False


def play_music(player, query, artist=None, album=None, song=None, shuffle=False, debug=False, max_depth=4, json_output=False):
    """Search and play music."""
    print(f"Searching for music...")

    api = _resolve_api(player)
    is_local = _is_local_player(player)

    parts = [query, artist, album, song]
    search_query = ' '.join(p for p in parts if p).strip()

    if api:
        response = api.audio_library_get_songs()
        if response and 'result' in response:
            songs = response['result'].get('songs', [])
            matches = []
            for s in songs:
                song_title = s.get('title', '').lower()
                song_artist = s.get('artist', [''])[0].lower() if s.get('artist') else ''
                song_album = s.get('album', '').lower()
                match = True
                if artist and artist.lower() not in song_artist:
                    match = False
                if album and album.lower() not in song_album:
                    match = False
                if song and song.lower() not in song_title:
                    match = False
                if match:
                    matches.append(s)

            if matches:
                if shuffle:
                    random.shuffle(matches)
                if len(matches) == 1:
                    s = matches[0]
                    print(f"\nPlaying: {s.get('title', 'Unknown')} by {s.get('artist', ['Unknown'])[0]}")
                    item = {'songid': s['songid']}
                    result = api.player_open_item(item)
                    print(json.dumps(result, indent=2))
                    return True
                else:
                    if json_output:
                        out = []
                        for i, s in enumerate(matches[:50], 1):
                            out.append({
                                "index": i,
                                "file": s.get('file', ''),
                                "label": s.get('title', 'Unknown'),
                                "artist": s.get('artist', [''])[0] if s.get('artist') else '',
                                "album": s.get('album', ''),
                            })
                        print(json.dumps(out, ensure_ascii=False))
                        return True
                    print(f"\nFound {len(matches)} library songs:")
                    for i, s in enumerate(matches[:50], 1):
                        artists = ', '.join(s.get('artist', ['Unknown']))
                        album_name = s.get('album', 'Unknown')
                        print(f"{i}. {s.get('title', 'Unknown')} - {artists} ({album_name})")
                    choice = input("\nEnter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit: ").strip()
                    sel = _parse_multi_selection(choice, len(matches))
                    if sel is None:
                        print("Invalid choice. Enter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit.")
                        return False
                    if len(sel) == 1:
                        s = matches[sel[0]]
                        print(f"\nPlaying: {s.get('title', 'Unknown')} by {s.get('artist', ['Unknown'])[0]}")
                        item = {'songid': s['songid']}
                        result = api.player_open_item(item)
                        print(json.dumps(result, indent=2))
                        return True
                    print(f"\nPlaying {len(sel)} songs...")
                    s = matches[sel[0]]
                    item = {'songid': s['songid']}
                    result = api.player_open_item(item)
                    for si in sel[1:]:
                        api.playlist_add(0, {'songid': matches[si]['songid']})
                    return True

    print("\nNo library match. Searching directories...")
    if api:
        remote_matches = search_all_remote_sources(api, search_query, 'music', debug=debug, max_depth=max_depth)
    elif is_local:
        remote_matches = local_search.search_all_local_sources(search_query, 'music', debug=debug, max_depth=max_depth)
    else:
        print("No player available.")
        return False

    if not remote_matches:
        print(f"No match found for '{query}'")
        return False

    if shuffle:
        random.shuffle(remote_matches)

    if len(remote_matches) == 1:
        m = remote_matches[0]
        print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
        if player:
            player.play_file(m['file'])
        else:
            api.player_open_item({'file': m['file']})
        return True
    else:
        if json_output:
            out = []
            for i, m in enumerate(remote_matches[:50], 1):
                out.append({
                    "index": i,
                    "file": m.get('file', ''),
                    "label": m.get('label', ''),
                    "display": m.get('display', ''),
                    "type": m.get('type', ''),
                    "source": m.get('source', ''),
                })
            print(json.dumps(out, ensure_ascii=False))
            return True
        print(f"\nFound {len(remote_matches)} matches:")
        for i, m in enumerate(remote_matches[:50], 1):
            print(f"{i}. [{m['source']}] {m.get('display', m['label'])}")
        choice = input("\nEnter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit: ").strip()
        if choice.lower() == 'q':
            return False
        elif choice.lower() == 'a':
            file_matches = [m for m in remote_matches if m.get('type') == 'file']
            dir_matches = [m for m in remote_matches if m.get('type') == 'directory']
            if file_matches:
                skipped = len(dir_matches)
                if skipped:
                    print(f"\nPlaying {len(file_matches)} songs (skipped {skipped} director(y/ies))...")
                else:
                    print(f"\nPlaying all {len(file_matches)} songs...")
                if player:
                    r = player.play_file(file_matches[0]['file'])
                    if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                        print(f"  Error: {r['error']}")
                    title = player.current_file()
                    if title:
                        print(f"  Playing: {title}")
                else:
                    api.player_open_item({'file': file_matches[0]['file']})
                for m in file_matches[1:]:
                    if player:
                        r = player.playlist_append(m['file'])
                        if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                            print(f"  Append error: {r['error']}")
                    else:
                        api.playlist_add(0, {'file': m['file']})
                return True
            elif dir_matches:
                print(f"\nNo individual files found, expanding {len(dir_matches)} director(y/ies)...")
                if player:
                    r = player.play_file(dir_matches[0]['file'])
                    if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                        print(f"  Error: {r['error']}")
                    title = player.current_file()
                    if title:
                        print(f"  Playing: {title}")
                else:
                    api.player_open_item({'file': dir_matches[0]['file']})
                for m in dir_matches[1:]:
                    if player:
                        r = player.playlist_append(m['file'])
                        if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                            print(f"  Append error: {r['error']}")
                    else:
                        api.playlist_add(0, {'file': m['file']})
                return True
            else:
                print("Nothing to play.")
                return False
        sel = _parse_multi_selection(choice, len(remote_matches))
        if sel is None:
            print("Invalid choice. Enter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit.")
            return False
        file_matches = [remote_matches[i] for i in sel if remote_matches[i].get('type') == 'file']
        dir_matches = [remote_matches[i] for i in sel if remote_matches[i].get('type') == 'directory']
        if file_matches:
            print(f"\nPlaying {len(file_matches)} songs...")
            if player:
                r = player.play_file(file_matches[0]['file'])
                if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                    print(f"  Error: {r['error']}")
                title = player.current_file()
                if title:
                    print(f"  Playing: {title}")
            else:
                api.player_open_item({'file': file_matches[0]['file']})
            for m in file_matches[1:]:
                if player:
                    r = player.playlist_append(m['file'])
                    if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                        print(f"  Append error: {r['error']}")
                else:
                    api.playlist_add(0, {'file': m['file']})
            return True
        elif dir_matches:
            print(f"\nPlaying {len(dir_matches)} director(y/ies)...")
            if player:
                r = player.play_file(dir_matches[0]['file'])
                if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                    print(f"  Error: {r['error']}")
                title = player.current_file()
                if title:
                    print(f"  Playing: {title}")
            else:
                api.player_open_item({'file': dir_matches[0]['file']})
            for m in dir_matches[1:]:
                if player:
                    r = player.playlist_append(m['file'])
                    if isinstance(r, dict) and r.get('error') not in (None, 'success'):
                        print(f"  Append error: {r['error']}")
                else:
                    api.playlist_add(0, {'file': m['file']})
            return True
        else:
            print("Nothing to play.")
            return False

    return False


def main():
    parser = argparse.ArgumentParser(description='Search and play media from KODI or local directories')
    parser.add_argument('--host', default='127.0.0.1', help='KODI host IP')
    parser.add_argument('--port', type=int, default=8080, help='KODI port')
    parser.add_argument('--username', default='', help='KODI username')
    parser.add_argument('--password', default='', help='KODI password')
    parser.add_argument('--protocol', choices=['tcp', 'http', 'auto'], default='auto', help='Connection protocol')
    parser.add_argument('--type', choices=['movie', 'tv', 'music', 'pvr'], required=True, help='Media type')
    parser.add_argument('--query', default='', help='Search query')
    parser.add_argument('--artist', default='', help='Artist name (music)')
    parser.add_argument('--album', default='', help='Album name (music)')
    parser.add_argument('--song', default='', help='Song name (music)')
    parser.add_argument('--shuffle', action='store_true', help='Shuffle playback (music)')
    parser.add_argument('--debug', action='store_true', help='Show debug output')
    parser.add_argument('--max-depth', type=int, default=4, help='Max recursion depth')
    parser.add_argument('--channel', default='', help='Channel name (PVR)')
    parser.add_argument('--local', action='store_true', help='Use local mpv mode (no KODI)')

    args = parser.parse_args()

    if args.local:
        from aiplayer.player import Player, PlayerMode
        player = Player(mode=PlayerMode.LOCAL)
    else:
        api = KodiAPI(args.host, args.port, args.username, args.password, protocol=args.protocol)
        version = api.get_version()
        if not version or 'result' not in version:
            print(f"Cannot connect to KODI at {args.host}:{args.port}")
            sys.exit(1)
        print(f"Connected to KODI v{version['result'].get('version', 'unknown')}")
        player = api

    if args.type == 'movie':
        success = play_movie(player, args.query, debug=args.debug, max_depth=args.max_depth)
    elif args.type == 'tv':
        success = play_tv_episode(player, args.query, debug=args.debug, max_depth=args.max_depth)
    elif args.type == 'music':
        success = play_music(player, args.query, args.artist, args.album, args.song,
                            args.shuffle, debug=args.debug, max_depth=args.max_depth)
    elif args.type == 'pvr':
        print("PVR playback not implemented in this script. Use pvr_epg.py instead.")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
