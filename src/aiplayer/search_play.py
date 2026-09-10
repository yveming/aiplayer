#!/usr/bin/env python3
"""
Search and play movies, TV shows, music from KODI or local directories.
Supports Player abstraction for KODI and local mpv modes.
"""

import json
import re
import os
import random
from collections import defaultdict

from aiplayer.player import \
    resolve_kodi_api as _resolve_api, is_local_player as _is_local_player
from aiplayer import local_search

try:
    from aiplayer.metadata import expand_titles, person_filmography
except Exception:
    expand_titles = person_filmography = None

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
    ctx = local_search.build_query_ctx(query, video_mode=video_mode, query_info=query_info)
    if not ctx[0]:
        return []

    def _entries(current_path, depth=0, path_stack=None):
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
                label = f_label or os.path.basename(f_path.rstrip('/'))
                full_stack = path_stack + [label]
                yield {
                    'label': label,
                    'display': ' / '.join(full_stack),
                    'file': f_path,
                    'type': 'directory',
                    'depth': depth,
                    'sXXeYY': extract_sXXeYY(f_label),
                }
                yield from _entries(f_path, depth + 1, full_stack)

            elif f_type == 'file':
                if extensions and not f_path.lower().endswith(extensions):
                    continue
                title_base = f_label or os.path.basename(f_path)
                title_no_ext = os.path.splitext(title_base)[0]
                full_stack = path_stack + [title_no_ext]
                yield {
                    'label': title_no_ext,
                    'display': ' / '.join(full_stack),
                    'file': f_path,
                    'type': 'file',
                    'depth': depth,
                    'sXXeYY': extract_sXXeYY(title_no_ext),
                }

    return local_search.match_entries(_entries(path), ctx)


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
        all_matches.extend(local_search.collect_matches(matches, extensions, src_label))

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

def _metadata_candidates(query, debug=False):
    """Expand query into Douban alias titles (best-effort, original excluded)."""
    if expand_titles is None:
        return []
    try:
        aliases = expand_titles(query, debug=debug)
    except Exception as e:
        if debug:
            print(f"  [debug] metadata expansion unavailable: {e}")
        return []
    return [a for a in aliases if a and a != query]


def _person_work_titles(query, debug=False):
    """Candidate work titles (Chinese + original) when query is a person."""
    if person_filmography is None:
        return []
    try:
        works = person_filmography(query, debug=debug)
    except Exception as e:
        if debug:
            print(f"  [debug] metadata person lookup unavailable: {e}")
        return []
    titles = []
    for w in works:
        for t in (w.get('title'), w.get('orig')):
            if t and t not in titles:
                titles.append(t)
    return titles


def _library_matches_with_aliases(query, candidates, debug=False):
    """Retry library fuzzy match with Douban aliases of the query."""
    for alias in _metadata_candidates(query, debug=debug):
        matches = fuzzy_match(alias, candidates)
        if matches:
            if debug:
                print(f"  [debug] Library match via alias: {alias!r}")
            return matches
    return []


def _person_library_matches(query, candidates, debug=False):
    """Match Douban filmography of a person query against library items."""
    titles = _person_work_titles(query, debug=debug)
    if not titles:
        return []
    results, seen = [], set()
    for t in titles:
        for score, c in fuzzy_match(t, candidates, threshold=0.75):
            key = c.get('movieid') or c.get('episodeid') or c.get('file')
            if key in seen:
                continue
            seen.add(key)
            results.append((score, c))
    results.sort(key=lambda x: x[0], reverse=True)
    if results:
        if debug:
            print(f"  [debug] Person match: {len(results)} item(s) for {query!r}")
        else:
            print(f"(matched works of: {query})")
    return results


def _tv_candidates(episodes):
    """Augment episode dicts so fuzzy_match keys on showtitle + SxxEyy."""
    out = []
    for e in episodes:
        c = dict(e)
        try:
            c['title'] = f"{e.get('showtitle', '')} S{int(e.get('season') or 0):02d}E{int(e.get('episode') or 0):02d}"
        except (TypeError, ValueError):
            c['title'] = e.get('showtitle', '')
        out.append(c)
    return out


def _person_dir_matches(query, api, is_local, media_type, max_depth=4,
                        tv_mode=False, query_info=None, debug=False):
    """Person fallback over a one-shot listing: local walk once or KODI library."""
    titles = _person_work_titles(query, debug=debug)
    if not titles:
        return []
    results = []
    if is_local and not api:
        entries = local_search.list_local_entries(media_type, max_depth=max_depth)
        if not entries:
            return []
        for t in titles:
            for score, e in fuzzy_match(t, entries, threshold=0.75):
                results.append((score, e))
    elif api:
        if media_type == 'movie':
            resp = api.video_library_get_movies()
            pool = resp['result'].get('movies', []) if resp and 'result' in resp else []
        else:
            resp = api.video_library_get_episodes()
            pool = _tv_candidates(resp['result'].get('episodes', [])) if resp and 'result' in resp else []
        for t in titles:
            for score, c in fuzzy_match(t, pool, threshold=0.75):
                results.append((score, c))
    else:
        return []
    if tv_mode and query_info and query_info.get('sXXeYY'):
        target = query_info['sXXeYY']
        filtered = []
        for score, e in results:
            sx = e.get('sXXeYY')
            if e.get('type') == 'file' and sx == target:
                filtered.append((score, e))
            elif e.get('type') == 'directory' and sx is None:
                filtered.append((score, e))
        results = filtered
    results.sort(key=lambda x: x[0], reverse=True)
    seen, out = set(), []
    for score, e in results:
        key = e.get('file') or e.get('movieid') or e.get('episodeid')
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    if out:
        if debug:
            print(f"  [debug] Person match: {len(out)} item(s) for {query!r}")
        else:
            print(f"(matched works of: {query})")
    return out


def _play_dir_match(player, api, m):
    """Play a directory-search match through the right backend."""
    if player:
        player.play_file(m['file'])
    else:
        api.player_open_item({'file': m['file']})


def _dir_json(remote_matches):
    return [{"index": i,
             "file": m.get('file', ''),
             "label": m.get('label', ''),
             "display": m.get('display', ''),
             "type": m.get('type', ''),
             "source": m.get('source', '')}
            for i, m in enumerate(remote_matches[:50], 1)]


def _present_dir_matches(remote_matches, player, api, json_output):
    """Handle single-match auto-play and --json for directory matches.

    Returns True when fully handled; None means the caller should run its
    own interactive selection UI.
    """
    if len(remote_matches) == 1 and not json_output:
        m = remote_matches[0]
        print(f"\nPlaying from {m['source']}: {m.get('display', m['label'])}")
        _play_dir_match(player, api, m)
        return True
    if json_output:
        print(json.dumps(_dir_json(remote_matches), ensure_ascii=False))
        return True
    return None


def _select_and_play_dir(remote_matches, player, api):
    """Numbered list + interactive pick for directory matches (movie/tv)."""
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
            _play_dir_match(player, api, m)
            return True
    except ValueError:
        pass
    print("Invalid choice.")
    return False


def _tv_label(episode):
    return (f"{episode.get('showtitle', 'Unknown')} - "
            f"S{episode.get('season', 0):02d}E{episode.get('episode', 0):02d}: "
            f"{episode.get('title', 'Unknown')}")


def _dirs_with_aliases(search_fn, primary_query, alias_source, debug=False):
    """Search directories; on empty result retry with Douban aliases."""
    matches = search_fn(primary_query)
    if not matches:
        for alias in _metadata_candidates(alias_source, debug=debug):
            matches = search_fn(alias)
            if matches:
                print(f"(matched via: {alias})")
                break
    return matches


def _handle_library_matches(matches, api, kind, json_output, allow_multi=False):
    """Unified single/--json/interactive handling for KODI library matches.

    kind: 'movie' | 'tv' | 'music'.  Returns True (consumed: played or JSON
    emitted), False (user aborted) or None (nothing selected - caller may
    fall through to directory search).
    """
    if kind == 'movie':
        def to_entry(i, m):
            entry = {"index": i, "file": m.get('file', ''), "label": m.get('title', 'Unknown')}
            if m.get('year'):
                entry["year"] = m.get('year')
            return entry
        def label_single(m):
            return m.get('title', 'Unknown')
        def label_pick(m):
            return f"{m.get('title', 'Unknown')} ({m.get('year', '')})"
        def list_line(m):
            return f"{m.get('title', 'Unknown')} ({m.get('year', '')})"
        def to_item(m):
            return {'movieid': m['movieid']}
        header = "library matches"
        prompt = "\nEnter number to play (or 'q' to quit): "
    elif kind == 'tv':
        def to_entry(i, m):
            return {"index": i, "file": m.get('file', ''), "label": _tv_label(m),
                    "showtitle": m.get('showtitle', 'Unknown'),
                    "season": m.get('season', 0), "episode": m.get('episode', 0)}
        label_single = label_pick = list_line = _tv_label
        def to_item(m):
            return {'episodeid': m['episodeid']}
        header = "library matches"
        prompt = "\nEnter number to play (or 'q' to quit): "
    else:
        def to_entry(i, m):
            return {"index": i, "file": m.get('file', ''), "label": m.get('title', 'Unknown'),
                    "artist": m.get('artist', [''])[0] if m.get('artist') else '',
                    "album": m.get('album', '')}
        def label_single(m):
            return f"{m.get('title', 'Unknown')} by {m.get('artist', ['Unknown'])[0]}"
        label_pick = label_single
        def list_line(m):
            return (f"{m.get('title', 'Unknown')} - "
                    f"{', '.join(m.get('artist', ['Unknown']))} ({m.get('album', 'Unknown')})")
        def to_item(m):
            return {'songid': m['songid']}
        header = "library songs"
        prompt = "\nEnter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit: "

    def play(item):
        result = api.player_open_item(item)
        print(json.dumps(result, indent=2))

    if len(matches) == 1 and not json_output:
        m = matches[0][1]
        print(f"\nPlaying: {label_single(m)}")
        play(to_item(m))
        return True
    if json_output:
        out = [to_entry(i, m) for i, (score, m) in enumerate(matches[:50], 1)]
        print(json.dumps(out, ensure_ascii=False))
        return True
    print(f"\nFound {len(matches)} {header}:")
    for i, (score, m) in enumerate(matches[:50], 1):
        print(f"{i}. {list_line(m)}")
    choice = input(prompt).strip()
    if choice.lower() == 'q':
        return False
    if allow_multi:
        sel = _parse_multi_selection(choice, len(matches))
        if sel is None:
            print("Invalid choice. Enter number(s) (e.g. 1,3,5 or 1-5), 'a' for all, 'q' to quit.")
            return False
        if len(sel) == 1:
            m = matches[sel[0]]
            print(f"\nPlaying: {label_pick(m)}")
            play(to_item(m))
            return True
        print(f"\nPlaying {len(sel)} songs...")
        play(to_item(matches[sel[0]]))
        for si in sel[1:]:
            api.playlist_add(0, {'songid': matches[si]['songid']})
        return True
    try:
        idx = int(choice) - 1
    except ValueError:
        print("Invalid choice.")
        return False
    if 0 <= idx < len(matches):
        m = matches[idx][1]
        print(f"\nPlaying: {label_pick(m)}")
        play(to_item(m))
        return True
    return None


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
            if not matches:
                matches = _library_matches_with_aliases(query, movies, debug=debug)
            if not matches:
                matches = _person_library_matches(query, movies, debug=debug)
            if matches:
                handled = _handle_library_matches(matches, api, 'movie', json_output)
                if handled is not None:
                    return handled

    if api:
        print("\nNo library match. Searching remote directories...")
        remote_matches = _dirs_with_aliases(
            lambda q: search_all_remote_sources(api, q, 'movie', debug=debug, max_depth=max_depth),
            base_query, base_query, debug=debug)
    elif is_local:
        print("\nNo KODI available. Searching local directories...")
        remote_matches = _dirs_with_aliases(
            lambda q: local_search.search_all_local_sources(q, 'movie', debug=debug, max_depth=max_depth),
            base_query, base_query, debug=debug)
    else:
        print("No player available.")
        return False

    if ordinal is not None and remote_matches:
        if debug:
            print(f"  [debug] Applying ordinal filter: pick 第{ordinal}部 in each directory")
        remote_matches = _pick_ordinal_files(remote_matches, ordinal, debug=debug)

    if not remote_matches:
        remote_matches = _person_dir_matches(query, api, is_local, 'movie',
                                             max_depth=max_depth, debug=debug)

    if not remote_matches:
        print(f"No match found for '{query}'")
        return False

    handled = _present_dir_matches(remote_matches, player, api, json_output)
    if handled:
        return True
    return _select_and_play_dir(remote_matches, player, api)


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
            if not matches:
                matches = _library_matches_with_aliases(query, _tv_candidates(episodes), debug=debug)
            if not matches:
                matches = _person_library_matches(query, _tv_candidates(episodes), debug=debug)
            if matches:
                handled = _handle_library_matches(matches, api, 'tv', json_output)
                if handled is not None:
                    return handled

    print("\nNo library match. Searching directories...")
    query_info = parse_tv_query(query)

    if api:
        remote_matches = _dirs_with_aliases(
            lambda q: search_all_remote_sources(
                api, q, 'video', debug=debug, max_depth=max_depth, video_mode=True,
                query_info=(query_info if q == query else dict(query_info, show=q))),
            query, query_info.get('show') or query, debug=debug)
    elif is_local:
        remote_matches = _dirs_with_aliases(
            lambda q: local_search.search_all_local_sources(
                q, 'video', debug=debug, max_depth=max_depth, video_mode=True,
                query_info=(query_info if q == query else dict(query_info, show=q))),
            query, query_info.get('show') or query, debug=debug)
    else:
        print("No player available.")
        return False

    if not remote_matches:
        remote_matches = _person_dir_matches(query, api, is_local, 'video',
                                             max_depth=max_depth, tv_mode=True,
                                             query_info=query_info, debug=debug)

    if not remote_matches:
        print(f"No match found for '{query}'")
        return False

    handled = _present_dir_matches(remote_matches, player, api, json_output)
    if handled:
        return True
    return _select_and_play_dir(remote_matches, player, api)


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
                handled = _handle_library_matches(matches, api, 'music', json_output, allow_multi=True)
                if handled is not None:
                    return handled

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

    handled = _present_dir_matches(remote_matches, player, api, json_output)
    if handled:
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
