#!/usr/bin/env python3
"""M3U parser + catch-up URL builder.

Reads a PVR IPTV Simple Client m3u file, extracts each channel's
`catchup-source` template, and provides a `build_catchup_url()` that
substitutes the common placeholder formats.

Placeholder families handled:

 1. KODI native (integer seconds since epoch)
    {start} {end} {duration} {timestamp} {utc} {lutc}
    {start_ms} {end_ms} {timestamp_ms}

 2. KODI native (YYYYMMDDHHMMSS strings)
    {utctime} {utcstart} {utcend} {localtime} {localstart} {localend}

 3. Strftime-style (iptvsimple's `${(b)...}` / `${(e)...}`)
    ${(b)yyyyMMddHHmmss}        - start time
    ${(e)yyyyMMddHHmmss}        - end time
    ${(b)yyyy-MM-dd HH:mm}      - any strftime pattern, local time

 4. VLC-style (`{name:strftime}`)
    {utc:YmdHMS}                - start, UTC
    {utcend:YmdHMS}             - end, UTC
    {lutc:YmdHMS}               - start, local
    {lutcend:YmdHMS}            - end, local
    {start:YmdHMS}              - alias for utc
    {end:YmdHMS}                - alias for utcend

A single m3u can mix these forms across channels - the AI checker
on the user's m3u flagged two formats co-existing.
"""
import gzip
import io
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def _read_text(source):
    """Read text from a local file path or HTTP(S) URL.

    Returns the decoded text.  Raises on network / IO errors.
    """
    if re.match(r'^https?://', source, re.IGNORECASE):
        with urllib.request.urlopen(source, timeout=10) as r:
            return r.read().decode('utf-8', errors='replace')
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    with open(source, 'r', encoding='utf-8') as f:
        return f.read()


def discover_m3u(base_url, channel_names, candidates=(
    'iptv-10.m3u', 'iptv-full.m3u', 'iptv-cmcc.m3u',
    'iptv.m3u', 'playlist.m3u',
)):
    """Pick the m3u under `base_url` whose channel list best matches
    `channel_names` (a list/iterable of label strings from KODI's
    PVR.GetChannels).

    Returns (best_name, best_entries, best_overlap) or (None, [], 0) on
    no match.  base_url can be a directory ('http://h:8000/iptv/') or
    a prefix without trailing slash.
    """
    base = base_url.rstrip('/') + '/'
    target_set = set(channel_names)
    best = (None, [], 0)
    for name in candidates:
        url = base + name
        try:
            text = _read_text(url)
        except Exception:
            continue
        entries = parse_m3u(text)
        names = {(e.get('tvg_name') or e.get('label') or '') for e in entries}
        overlap = len(target_set & names)
        if overlap > best[2]:
            best = (url, entries, overlap)
    return best


# ── XMLTV EPG ──────────────────────────────────────────────────────
#
# Standard XMLTV format:
#   <channel id="..."><display-name lang="zh">...</display-name></channel>
#   <programme channel="..." start="20260531011100 +0800"
#              stop="20260531015500 +0800">
#       <title>...</title>
#   </programme>
# The `start`/`stop` formats are `YYYYMMDDHHMMSS ±HHMM` and may be
# gzipped.


def _parse_xmltv_time(s):
    """Parse '20260531011100 +0800' or '20260531011100' -> tz-aware
    datetime (interpreted as UTC if no offset given)."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r'^(\d{14})(?:\s+([+-]\d{4}))?', s)
    if not m:
        return None
    body, tzoff = m.group(1), m.group(2)
    dt = datetime.strptime(body, '%Y%m%d%H%M%S')
    if tzoff:
        sign = 1 if tzoff[0] == '+' else -1
        hh = int(tzoff[1:3])
        mm = int(tzoff[3:5])
        from datetime import timedelta as _td
        dt = dt.replace(tzinfo=timezone(sign * _td(hours=hh, minutes=mm)))
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_xmltv(source):
    """Parse an XMLTV file (gzipped or not) from a URL or local path.

    Returns:
      channels:  {channel_id: display_name}
      programs:  list of dicts
                 {channel, start_utc, end_utc, title}
                 where start/end are tz-aware datetimes in UTC.

    `source` can be a local file path or an http(s) URL.
    """
    if re.match(r'^https?://', source, re.IGNORECASE):
        with urllib.request.urlopen(source, timeout=15) as r:
            raw = r.read()
    else:
        with open(source, 'rb') as f:
            raw = f.read()
    # Try to gunzip; fall back to raw.
    try:
        decompressed = gzip.decompress(raw)
    except (OSError, EOFError, gzip.BadGzipFile):
        decompressed = raw
    root = ET.parse(io.BytesIO(decompressed)).getroot()

    channels = {}
    for c in root.findall('channel'):
        cid = c.get('id', '')
        name_el = c.find('display-name')
        name = name_el.text if name_el is not None else cid
        channels[cid] = name

    programs = []
    for p in root.findall('programme'):
        cid = p.get('channel', '')
        start = _parse_xmltv_time(p.get('start', ''))
        end = _parse_xmltv_time(p.get('stop', ''))
        if not (start and end):
            continue
        # Normalise to UTC for downstream comparison.
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        title_el = p.find('title')
        title = title_el.text if title_el is not None else ''
        programs.append({
            'channel': cid,
            'start_utc': start_utc,
            'end_utc': end_utc,
            'title': title,
        })
    return channels, programs


def get_x_tvg_url(m3u_text):
    """Pull `x-tvg-url` from the #EXTM3U line, if present."""
    for line in m3u_text.splitlines()[:3]:
        if line.startswith('#EXTM3U'):
            m = re.search(r'x-tvg-url="([^"]*)"', line)
            if m:
                return m.group(1)
    return None


def find_program_in_xmltv(programs, channel_id, target_local_dt):
    """Find the XMLTV <programme> on `channel_id` covering
    `target_local_dt` (a tz-aware datetime in the user's local tz).

    Returns the program dict or None.
    """
    target_utc = target_local_dt.astimezone(timezone.utc)
    target_local_day = target_local_dt.date()
    for p in programs:
        if p['channel'] != channel_id:
            continue
        if p['start_utc'] <= target_utc < p['end_utc']:
            # Same day requirement (match KODI's find_program_in_epg).
            local_start = p['start_utc'].astimezone(target_local_dt.tzinfo)
            if local_start.date() != target_local_day:
                continue
            return p
    return None


# VLC-style placeholder: {name:strftime}  e.g. {utc:YmdHMS}
_RE_VLC = re.compile(r'\{(utcend|utctime|utcstart|lutcend|lutctime|lutcstart|'
                     r'utc|lutc|start|end|now|ts|duration):([^}]+)\}')

# iptvsimple strftime-style: ${(b)...} or ${(e)...}
_RE_STRFTIME = re.compile(r'\$\{\((b|e)\)([^}]*)\}')


_M3U_EXTINF = re.compile(r'#EXTINF[^\n]*', re.IGNORECASE)


def parse_m3u(text):
    """Parse m3u text. Returns list of dicts:
        {label, tvg_name, tvg_id, catchup_source, stream_url, group}
    The stream_url is the line that follows the #EXTINF (live URL).
    catchup_source is None if the channel has no #EXTINF catchup-source.
    """
    out = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#EXTM3U'):
            continue
        if line.startswith('#EXTINF'):
            pending = _parse_extinf(line)
        elif line.startswith('#'):
            # #EXTGRP, #EXTVLCOPT, etc - we ignore but preserve pending
            continue
        else:
            # First non-comment line after #EXTINF is the stream URL
            if pending is not None:
                pending['stream_url'] = line
                out.append(pending)
                pending = None
            else:
                # URL without preceding #EXTINF - skip
                continue
    return out


def _parse_extinf(line):
    """Parse one #EXTINF line into a dict."""
    d = {
        'label': '',
        'tvg_name': None,
        'tvg_id': None,
        'catchup_source': None,
        'catchup_days': None,
        'group': None,
        'stream_url': None,
    }
    # The label is after the last comma
    if ',' in line:
        d['label'] = line.rsplit(',', 1)[-1].strip()
    # Attribute-style key="value"
    for key in ('tvg-name', 'tvg-id', 'catchup-source', 'catchup-days',
                'group-title'):
        m = re.search(rf'{key}="([^"]*)"', line, re.IGNORECASE)
        if m:
            camel = key.replace('-', '_')
            d[camel] = m.group(1)
    return d


def find_channel(entries, name):
    """Find an m3u entry by tvg-name or label. Returns the entry or None."""
    if not name:
        return None
    nl = name.lower()
    # 1) exact tvg-name or label
    for e in entries:
        if (e.get('tvg_name') and e['tvg_name'] == name) or e.get('label') == name:
            return e
    # 2) case-insensitive
    for e in entries:
        if (e.get('tvg_name') and e['tvg_name'].lower() == nl) or \
           (e.get('label') and e['label'].lower() == nl):
            return e
    # 3) substring
    for e in entries:
        for f in ('tvg_name', 'label'):
            v = e.get(f) or ''
            if name in v or nl in v.lower():
                return e
    return None


def build_catchup_url(template, start_utc, end_utc, local_tz=None,
                      catchup_id=None):
    """Substitute placeholders in `template` with the broadcast's times.

    start_utc / end_utc are tz-aware datetimes in UTC.  Supports every
    placeholder format commonly seen in m3u `catchup-source` lines.
    All format placeholders are filled with box-local wall clock time
    (mirrors KODI pvr.iptvsimple's actual behaviour), even {utc:}-named ones.
    """
    if not template:
        return None
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)
    if local_tz is None:
        local_tz = timezone.utc

    start_sec = int(start_utc.timestamp())
    end_sec = int(end_utc.timestamp())
    duration_sec = max(0, end_sec - start_sec)

    start_utc_str = start_utc.strftime('%Y%m%d%H%M%S')
    end_utc_str = end_utc.strftime('%Y%m%d%H%M%S')
    start_local_str = start_utc.astimezone(local_tz).strftime('%Y%m%d%H%M%S')
    end_local_str = end_utc.astimezone(local_tz).strftime('%Y%m%d%H%M%S')

    url = template

    # ── Family 1: KODI seconds-since-epoch ──
    url = url.replace('{start}', str(start_sec))
    url = url.replace('{end}', str(end_sec))
    url = url.replace('{duration}', str(duration_sec))
    url = url.replace('{timestamp}', str(start_sec))
    url = url.replace('{utc}', str(start_sec))
    url = url.replace('{lutc}', str(start_sec))
    url = url.replace('{start_ms}', str(start_sec * 1000))
    url = url.replace('{end_ms}', str(end_sec * 1000))
    url = url.replace('{timestamp_ms}', str(start_sec * 1000))

    # ── Family 2: YYYYMMDDHHMMSS strings ──
    url = url.replace('{utctime}', start_local_str)
    url = url.replace('{utcstart}', start_local_str)
    url = url.replace('{utcend}', end_local_str)
    url = url.replace('{localtime}', start_local_str)
    url = url.replace('{localstart}', start_local_str)
    url = url.replace('{localend}', end_local_str)

    # ── Family 3: iptvsimple strftime-style  ${(b)fmt} / ${(e)fmt} ──
    # (b) = beginning, (e) = end. fmt is a strftime pattern.
    def _repl_strftime(m):
        marker = m.group(1)           # 'b' or 'e'
        fmt = m.group(2)
        # ${(b)fmt} uses local time (iptvsimple default).
        # ${(e)fmt} uses local time.
        dt = start_utc.astimezone(local_tz) if marker == 'b' \
            else end_utc.astimezone(local_tz)
        try:
            return dt.strftime(_cvt_strftime(fmt))
        except ValueError:
            return m.group(0)
    url = _RE_STRFTIME.sub(_repl_strftime, url)

    # ── Family 4: VLC-style {name:fmt} ──
    def _repl_vlc(m):
        name = m.group(1).lower()
        fmt = m.group(2)
        # Pick the time the placeholder refers to.
        if name in ('utcend', 'end', 'lutcend'):
            dt = end_utc
        elif name in ('utctime', 'utcstart', 'utc', 'lutc', 'lutcstart',
                      'lutctime', 'start', 'ts', 'now'):
            dt = start_utc
        elif name == 'duration':
            return str(duration_sec)
        else:
            return m.group(0)
        # Mirror KODI pvr.iptvsimple's actual behaviour: ALL format
        # placeholders are filled with box-local wall clock time, even the
        # {utc:}-named ones (field-verified against real IPTV backends).
        dtu = dt.astimezone(local_tz)
        try:
            return dtu.strftime(_cvt_strftime(fmt))
        except ValueError:
            return m.group(0)
    url = _RE_VLC.sub(_repl_vlc, url)

    # ── Channel catchup id (caller provides) ──
    if catchup_id is not None:
        url = url.replace('{catchup-id}', catchup_id)
        url = url.replace('{catchupid}', catchup_id)

    return url


# VLC/iptvsimple strftime tokens.  Multi-char tokens (yyyy, MM, HH, ...)
# are listed first so longest-match wins.  Single-char tokens match
# any single letter that's part of a longer pattern, so we feed this
# into a regex with longest-match-first.
_STRFTIME_TOKENS = [
    ('yyyy', '%Y'), ('YYYY', '%Y'),
    ('yy',   '%y'), ('YY',   '%y'),
    ('MM',   '%m'), ('mm',   '%M'),
    ('dd',   '%d'), ('DD',   '%d'),
    ('HH',   '%H'), ('hh',   '%I'),
    ('ss',   '%S'), ('SS',   '%S'),
    ('M',    '%M'), ('m',    '%m'),
    ('D',    '%d'), ('d',    '%d'),
    ('H',    '%H'), ('h',    '%I'),
    ('S',    '%S'), ('s',    '%S'),
    ('Y',    '%Y'), ('y',    '%y'),
    ('a',    '%a'), ('A',    '%A'),
    ('b',    '%b'), ('B',    '%B'),
    ('p',    '%p'), ('I',    '%I'),
    ('j',    '%j'), ('U',    '%U'), ('W',    '%W'), ('w',    '%w'),
    ('z',    '%z'), ('Z',    '%Z'),
    ('c',    '%c'), ('x',    '%x'), ('X',    '%X'),
]
_STRFTIME_TOKEN_PAT = '|'.join(re.escape(t) for t, _ in _STRFTIME_TOKENS)
_STRFTIME_RE = re.compile(r'%.|' + _STRFTIME_TOKEN_PAT)
_STRFTIME_LOOKUP = dict(_STRFTIME_TOKENS)


def _cvt_strftime(fmt):
    """Convert VLC/iptvsimple strftime shorthand to Python strftime.

    VLC uses `yyyy` for 4-digit year, `MM` for month, `mm` for minute,
    etc.  Python's strftime uses single chars with `%` prefix.  This
    function tokenises the format with longest-match-first, leaving
    existing `%x` sequences alone.
    """
    def _repl(m):
        tok = m.group(0)
        if tok.startswith('%'):
            return tok
        return _STRFTIME_LOOKUP.get(tok, tok)
    return _STRFTIME_RE.sub(_repl, fmt)
