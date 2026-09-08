#!/usr/bin/env python3
"""
Filesystem-based media search for local directories (CIFS/NFS mounts).
Replicates the matching logic from search_play.py using os.walk.
"""

import os
import re
from pathlib import Path
from difflib import SequenceMatcher

VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.mpg', '.mpeg', '.iso', '.img')
AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.wma', '.ape', '.cue')

CHINESE_NUMERALS = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
}

_CHINESE_PATH_PARTICLES = '的之'
_PATH_PUNCTUATION = '()[]{}!?,.;:\'"-\\/<>《》【】'


def _chinese_to_int(s):
    if s is None:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    return CHINESE_NUMERALS.get(s)


def parse_tv_query(query):
    q = (query or '').strip()
    result = {'show': q, 'season': None, 'episode': None, 'sXXeYY': None, 'raw': q}
    if not q:
        return result

    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', q)
    if not m:
        m = re.search(r'(\d{1,2})\s*[xX]\s*(\d{1,2})', q)
    if not m:
        m = re.search(
            r'第\s*(\d+|[零一二三四五六七八九十]{1,3})\s*季'
            r'.*?第\s*(\d+|[零一二三四五六七八九十]{1,3})\s*集',
            q,
        )
    if m:
        season = _chinese_to_int(m.group(1))
        episode = _chinese_to_int(m.group(2))
        if season is not None and episode is not None:
            result['show'] = q[:m.start()].strip(' ._-/[]()')
            result['season'] = season
            result['episode'] = episode
            result['sXXeYY'] = f'S{season:02d}E{episode:02d}'
    return result


def extract_sXXeYY(label):
    if not label:
        return None
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', label)
    return f'S{int(m.group(1)):02d}E{int(m.group(2)):02d}' if m else None


def extract_movie_ordinal(query):
    if not query:
        return None
    m = re.search(r'第([零一二三四五六七八九十百\d]+)', query)
    if m:
        num_str = m.group(1)
        if num_str.isdigit():
            n = int(num_str)
            if 1 <= n <= 99:
                return n
        else:
            n = _chinese_to_int(num_str)
            if n is not None and 1 <= n <= 99:
                return n
    m = re.search(r'([''一二三四五六七八九十])$', query)
    if m:
        n = _chinese_to_int(m.group(1))
        if n is not None and 1 <= n <= 10:
            return n
    m = re.search(r'(?<!\d)(\d{1,2})$', query)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 99:
            return n
    return None


def strip_movie_ordinal(query):
    if not query:
        return query
    new = re.sub(r'第[零一二三四五六七八九十百\d]+[部集个]?', '', query)
    if new != query:
        return new.strip()
    new = re.sub(r'[''一二三四五六七八九十]$', '', query)
    if new != query:
        return new.strip()
    new = re.sub(r'(?<!\d)\d{1,2}$', '', query)
    if new != query:
        return new.strip()
    return query


_MOVIE_YEAR_RE = re.compile(r'(?<!\d)(19|20)\d{2}(?!\d)')


def extract_movie_year(label):
    if not label:
        return None
    m = _MOVIE_YEAR_RE.search(label)
    return int(m.group(0)) if m else None


def _strip_path_particles(s):
    return ''.join(ch for ch in (s or '') if ch not in _CHINESE_PATH_PARTICLES)


def _normalize_for_match(s):
    if not s:
        return s
    s = _strip_path_particles(s)
    for c in _PATH_PUNCTUATION:
        s = s.replace(c, '')
    s = s.replace(' ', '')
    return s.lower()


DEFAULT_MEDIA_ROOTS = {
    'movie': [r'G:\movie', '/mnt/media/movie', '/media/movie', '/mnt/movie'],
    'video': [r'G:\video', '/mnt/media/video', '/media/video', '/mnt/video'],
    'music': [r'G:\music', '/mnt/media/music', '/media/music', '/mnt/music'],
}


def _get_media_roots(media_type='movie'):
    dirs = DEFAULT_MEDIA_ROOTS.get(media_type, [])
    results = []
    for d in dirs:
        p = Path(d)
        if p.is_dir():
            results.append(p)
    return results


def find_local_media_roots():
    """Discover existing local media directories by probing common paths."""
    found = {'movie': [], 'video': [], 'music': []}
    for media_type, dirs in DEFAULT_MEDIA_ROOTS.items():
        for d in dirs:
            p = Path(d)
            if p.is_dir():
                found[media_type].append(p)
    return found


def search_local_directory(root_path, query, extensions=None, max_depth=4, debug=False,
                           video_mode=False, query_info=None):
    """Recursively search a local directory for files matching query.

    Same matching logic as search_play.search_remote_directory but
    uses local filesystem (os.walk / Path.rglob).
    """
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

    show_fallback = _strip_path_particles(
        query if not (video_mode and query_info)
        else (query_info.get('show') or '')
    ).replace(' ', '').lower()

    if not show_norm:
        return matches

    root = Path(root_path)
    if not root.is_dir():
        return matches

    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts) if str(rel) != '.' else 0
        if depth > max_depth:
            dirnames.clear()
            continue

        path_stack = list(rel.parts) if str(rel) != '.' else []

        # Check directory itself
        dir_label = os.path.basename(dirpath)
        full_norm = _normalize_for_match(''.join(path_stack)) if path_stack else ''
        full_fallback = _strip_path_particles(''.join(path_stack)).replace(' ', '').lower() if path_stack else ''
        dir_matched = (show_norm and full_norm and show_norm in full_norm) or \
                      (show_fallback and full_fallback and show_fallback in full_fallback)

        if dir_matched and path_stack:
            matches.append({
                'label': dir_label,
                'display': ' / '.join(path_stack),
                'file': dirpath,
                'type': 'directory',
                'depth': depth,
                'sXXeYY': extract_sXXeYY(dir_label),
            })

        for fname in filenames:
            label_no_ext = os.path.splitext(fname)[0]
            full_stack = path_stack + [label_no_ext]
            full_norm = _normalize_for_match(''.join(full_stack))
            full_fallback = _strip_path_particles(''.join(full_stack)).replace(' ', '').lower()

            if show_norm not in full_norm and show_fallback not in full_fallback:
                continue

            fpath = os.path.join(dirpath, fname)
            f_ext = os.path.splitext(fname)[1].lower()
            if extensions and f_ext not in extensions:
                continue

            matches.append({
                'label': label_no_ext,
                'display': ' / '.join(full_stack),
                'file': fpath,
                'type': 'file',
                'depth': depth,
                'sXXeYY': extract_sXXeYY(label_no_ext),
            })

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


def search_all_local_sources(query, media_type='video', debug=False,
                             video_mode=False, query_info=None, max_depth=4):
    """Search all local media directories for matching files."""
    roots = _get_media_roots(media_type)
    all_matches = []

    extensions = VIDEO_EXTENSIONS if media_type in ('movie', 'tv', 'video') else AUDIO_EXTENSIONS

    if debug:
        print(f"  [debug] Local search: query='{query}' media='{media_type}' roots={[str(r) for r in roots]}")

    for root in roots:
        matches = search_local_directory(
            root, query, None, max_depth=max_depth,
            debug=debug, video_mode=video_mode, query_info=query_info,
        )
        if debug:
            print(f"  [debug] Searched '{root}': {len(matches)} candidate(s)")
        for m in matches:
            if m['type'] == 'file' and extensions:
                ext = os.path.splitext(m['file'])[1].lower()
                if ext not in extensions:
                    continue
            m['source'] = str(root)
            all_matches.append(m)

    return all_matches


def fuzzy_match(query, candidates, threshold=0.6):
    results = []
    query_lower = query.lower()
    for candidate in candidates:
        title = candidate.get('title', candidate.get('label', ''))
        if not title:
            continue
        if query_lower in title.lower() or title.lower() in query_lower:
            results.append((1.0, candidate))
            continue
        query_words = set(query_lower.split())
        title_words = set(title.lower().split())
        if query_words and query_words.issubset(title_words):
            results.append((0.9, candidate))
            continue
        ratio = SequenceMatcher(None, query_lower, title.lower()).ratio()
        if ratio >= threshold:
            results.append((ratio, candidate))
    results.sort(key=lambda x: x[0], reverse=True)
    return results
