#!/usr/bin/env python3
"""
Online metadata expansion via Douban web endpoints (unofficial).

Best-effort only: every network call is wrapped; any failure returns
empty results so callers silently fall back to local-only search.

Endpoints used:
  - subject suggest:  https://movie.douban.com/j/subject_suggest?q=<kw>
  - person works:     https://movie.douban.com/j/search_subjects?type=<movie|tv>&tag=<name>
                      (Douban tags include cast/crew names; JSON, not anti-bot protected)
"""

import requests

from aiplayer.config import load_config

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

_SUGGEST_URL = 'https://movie.douban.com/j/subject_suggest'
_TAG_SEARCH_URL = 'https://movie.douban.com/j/search_subjects'

_MAX_SUGGEST_ITEMS = 3
_MAX_WORKS = 50


def _settings():
    """(enabled, timeout) from config 'metadata' section, with sane defaults."""
    md = load_config(quiet=True).get('metadata', {})
    enabled = md.get('enabled', True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ('1', 'true', 'yes', 'on')
    try:
        timeout = max(1.0, float(md.get('timeout', 5)))
    except (TypeError, ValueError):
        timeout = 5.0
    return bool(enabled), timeout


def _get(url, params=None, timeout=5.0, debug=False):
    headers = {
        'User-Agent': _UA,
        'Referer': 'https://movie.douban.com/',
        'Accept': 'application/json, text/plain, */*',
    }
    r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r


def suggest(query, debug=False):
    """Douban subject suggest. Returns a raw list of suggestion dicts.

    Item types: 'movie' / 'tv' (keys: title, sub_title, year, id)
                'celebrity'     (keys: title, id, url)
    """
    enabled, timeout = _settings()
    if not enabled or not (query or '').strip():
        return []
    try:
        r = _get(_SUGGEST_URL, params={'q': query.strip()}, timeout=timeout)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        if debug:
            print(f"  [debug] Douban suggest failed: {e}")
        return []


def expand_titles(query, debug=False):
    """Return [original, ...alias titles] for a movie/TV query via Douban.

    Aliases come from the suggested subjects' Chinese title (title) and
    original/foreign title (sub_title), enabling multi-language matching.
    """
    titles = [query]
    seen = {query.strip().lower()}
    for item in suggest(query, debug=debug)[:_MAX_SUGGEST_ITEMS]:
        if item.get('type') not in ('movie', 'tv'):
            continue
        for key in ('title', 'sub_title'):
            val = (item.get(key) or '').strip()
            if val and val.lower() not in seen:
                seen.add(val.lower())
                titles.append(val)
    if debug:
        print(f"  [debug] Douban expand_titles({query!r}) -> {titles}")
    return titles


def person_filmography(name, debug=False, limit=_MAX_WORKS):
    """If `name` matches a Douban celebrity, return [{'title','orig'}, ...].

    Works are collected via Douban tag search (movies + TV tagged with the
    person's name). Titles are Chinese display titles; 'orig' stays empty
    (tag search carries no foreign-title field).
    """
    enabled, timeout = _settings()
    if not enabled or not (name or '').strip():
        return []
    q = name.strip()
    if not any(item.get('type') == 'celebrity' for item in suggest(q, debug=debug)):
        if debug:
            print(f"  [debug] Douban: no celebrity match for {q!r}")
        return []
    works, seen = [], set()
    for stype, page_size in (('movie', 30), ('tv', 20)):
        try:
            r = _get(_TAG_SEARCH_URL,
                     params={'type': stype, 'tag': q, 'sort': 'recommendation',
                             'page_limit': page_size, 'page_start': 0},
                     timeout=timeout)
            data = r.json()
            items = data.get('subjects') or [] if isinstance(data, dict) else []
        except Exception as e:
            if debug:
                print(f"  [debug] Douban tag search ({stype}) failed: {e}")
            continue
        for it in items:
            title = (it.get('title') or '').strip()
            if title and title.lower() not in seen:
                seen.add(title.lower())
                works.append({'title': title, 'orig': ''})
            if len(works) >= limit:
                break
        if len(works) >= limit:
            break
    if debug:
        print(f"  [debug] Douban filmography {q!r}: {len(works)} work(s)")
    return works


if __name__ == '__main__':
    import sys
    q = ' '.join(sys.argv[1:]) or '肖申克的救赎'
    print(f"expand_titles({q!r}):")
    for t in expand_titles(q, debug=True):
        print(f"  - {t}")
    print(f"person_filmography({q!r}):")
    for w in person_filmography(q, debug=True)[:10]:
        print(f"  - {w['title']}" + (f"  [{w['orig']}]" if w['orig'] else ''))