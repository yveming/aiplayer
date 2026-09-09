#!/usr/bin/env python3
"""
Configuration management for aiplayer.

Config file: ~/.config/aiplayer/config.json
Auto-generated with defaults on first run. All values are optional;
empty values mean "not configured" and callers fall back to hints.
Precedence: CLI flags > config file > built-in defaults.
"""

import copy
import json
import os

CONFIG_FILE_NAME = 'config.json'

DEFAULT_CONFIG = {
    "kodi": {
        "host": "",
        "port": 0,
        "username": "",
        "password": "",
        "protocol": "auto",
    },
    "iptv": {
        "m3u": "",
        "epg": "",
    },
    "mpv": {
        "path": "",
    },
    "media": {
        "movie": [],
        "video": [],
        "music": [],
    },
    "metadata": {
        "enabled": True,
        "timeout": 5,
    },
}

_COMMENT = (
    "aiplayer config. Empty string/list = not configured. "
    "iptv.m3u: IPTV m3u, http(s):// URL or local file path. "
    "iptv.epg: XMLTV EPG, http(s):// URL or local file path. "
    "media.*: local media root directories (no built-in defaults). "
    "kodi.*: KODI connection defaults. mpv.path: mpv executable. "
    "metadata: online Douban expansion (enabled, timeout seconds). "
    "CLI flags override these values."
)


def get_config_dir():
    return os.path.join(os.path.expanduser('~'), '.config', 'aiplayer')


def get_config_path():
    return os.path.join(get_config_dir(), CONFIG_FILE_NAME)


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if key == '_comment':
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _generate_default(path):
    data = copy.deepcopy(DEFAULT_CONFIG)
    data['_comment'] = _COMMENT
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def _normalize(merged):
    kodi = merged.setdefault('kodi', {})
    port = kodi.get('port')
    if not isinstance(port, int) or isinstance(port, bool):
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 0
    kodi['port'] = port
    for section in ('iptv', 'mpv'):
        sec = merged.setdefault(section, {})
        for key, val in list(sec.items()):
            sec[key] = '' if val is None else str(val)
    media = merged.setdefault('media', {})
    for key, val in list(media.items()):
        if isinstance(val, str):
            val = [val] if val else []
        elif isinstance(val, list):
            val = [str(x) for x in val if x]
        else:
            val = []
        media[key] = val
    md = merged.setdefault('metadata', {})
    enabled = md.get('enabled', True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ('1', 'true', 'yes', 'on')
    md['enabled'] = bool(enabled)
    try:
        md['timeout'] = max(1.0, float(md.get('timeout', 5)))
    except (TypeError, ValueError):
        md['timeout'] = 5.0
    return merged


def load_config(path=None, quiet=False):
    """Load config.json, auto-generating defaults on first run.

    Never raises: on unreadable/corrupt files it warns and returns defaults.
    """
    path = path or get_config_path()
    if not os.path.exists(path):
        try:
            _generate_default(path)
            if not quiet:
                print(f"Config created: {path}")
        except OSError as e:
            if not quiet:
                print(f"Warning: cannot create config {path}: {e}")
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Warning: cannot read config {path} ({e}); using defaults.")
        return copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        print(f"Warning: config {path} is not a JSON object; using defaults.")
        return copy.deepcopy(DEFAULT_CONFIG)
    return _normalize(_deep_merge(DEFAULT_CONFIG, data))


def media_config_hint():
    return ("No media directories configured.\n"
            "Edit " + get_config_path() +
            ' -> "media": {"movie": [...], "video": [...], "music": [...]}')


def epg_config_hint():
    return ("No EPG URL. Set \"iptv\": {\"epg\": \"...\"} in " +
            get_config_path() + " or pass --epg.")


if __name__ == '__main__':
    print(f"Config path: {get_config_path()}")
    cfg = load_config()
    print(json.dumps(cfg, indent=2, ensure_ascii=False))