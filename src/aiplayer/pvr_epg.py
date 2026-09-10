#!/usr/bin/env python3
"""
PVR channel browsing, EPG lookup, and catch-up TV.
Supports Player abstraction for KODI and local mpv playback.
"""

import re
from datetime import datetime, timedelta, timezone

from aiplayer.m3u_catchup import parse_m3u, find_channel as m3u_find_channel, build_catchup_url
from aiplayer.m3u_catchup import (parse_xmltv, get_x_tvg_url, find_program_in_xmltv,
                         _read_text as m3u_read_text)
from aiplayer.player import resolve_kodi_api

LOCAL_TZ = timezone(timedelta(hours=8))
from aiplayer.config import load_config, epg_config_hint


def get_all_channels(api):
    """Get all PVR channels from all channel groups (KODI only)."""
    all_channels = []
    seen = set()
    groups_response = api.pvr_get_channel_groups()
    if not groups_response or 'result' not in groups_response:
        print("No channel groups found or error occurred.")
        return []
    groups = groups_response['result'].get('channelgroups', [])
    for group in groups:
        group_id = group.get('channelgroupid', 1)
        group_label = group.get('label', 'Unknown')
        channels_response = api.pvr_get_channels(channel_group_id=group_id)
        if channels_response and 'result' in channels_response:
            for ch in channels_response['result'].get('channels', []):
                cid = ch.get('channelid')
                if cid in seen:
                    continue
                seen.add(cid)
                ch['group'] = group_label
                all_channels.append(ch)
    return all_channels


def find_channel_by_name(channels, name):
    if not name:
        return None
    name_lower = name.lower()
    for ch in channels:
        label = ch.get('label', '') or ''
        if label == name:
            return ch
    for ch in channels:
        label = (ch.get('label', '') or '').lower()
        if label == name_lower:
            return ch
    for ch in channels:
        label = ch.get('label', '') or ''
        if name in label or name_lower in label.lower():
            return ch
    return None


_CN_NUMS = {'零':0,'〇':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
def _cn2num(s):
    s = s.strip()
    if not s:
        return None
    if s in _CN_NUMS:
        return _CN_NUMS[s]
    # ten-based: 十一 (11), 二十 (20), 二十一 (21), 一百 (100)
    total = 0
    buf = 0
    for ch in s:
        if ch in _CN_NUMS:
            v = _CN_NUMS[ch]
            if v == 10:
                total += (buf if buf else 1) * 10
                buf = 0
            else:
                buf = v
        else:
            return None
    return total + buf


def parse_time(time_str, default_tz='utc'):
    if not time_str:
        return None
    local_tz = LOCAL_TZ
    default = timezone.utc if default_tz == 'utc' else local_tz
    s = time_str.strip()
    sl = s.lower()

    if sl in ('now', '现在', '当前'):
        return datetime.now(default)
    if sl in ('today', '今天'):
        return datetime.now(default).replace(hour=0, minute=0, second=0, microsecond=0)
    if sl in ('yesterday', '昨天'):
        return (datetime.now(default) - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('tomorrow', '明天'):
        return (datetime.now(default) + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('day_before_yesterday', '前天'):
        return (datetime.now(default) - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('day_after_tomorrow', '后天'):
        return (datetime.now(default) + timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0)

    s_iso = s.replace('Z', '+00:00') if s.endswith('Z') else s
    try:
        dt = datetime.fromisoformat(s_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default)
        return dt
    except ValueError:
        pass

    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%H:%M:%S', '%H:%M'):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default)
            return dt
        except ValueError:
            continue

    # Chinese time: '8点30分', '十点', '十点三十分', '8点半'
    import re
    m = re.match(r'^(\d{1,2})点(\d{1,2})分$', s)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        n = datetime.now(default)
        return n.replace(hour=h, minute=mn, second=0, microsecond=0)
    m = re.match(r'^(\d{1,2})点半$', s)
    if m:
        h = int(m.group(1))
        n = datetime.now(default)
        return n.replace(hour=h, minute=30, second=0, microsecond=0)
    m = re.match(r'^(\d{1,2})点', s)
    if m:
        h = int(m.group(1))
        n = datetime.now(default)
        return n.replace(hour=h, minute=0, second=0, microsecond=0)
    # Chinese numerals: '十点', '十点三十分', '八点', '八点十分'
    m = re.match(r'^([\u4e00-\u9fff]+)点([\u4e00-\u9fff]+)分', s)
    if m:
        h = _cn2num(m.group(1))
        mn = _cn2num(m.group(2))
        if h is not None and mn is not None:
            n = datetime.now(default)
            return n.replace(hour=h, minute=mn, second=0, microsecond=0)
    m = re.match(r'^([\u4e00-\u9fff]+)点([\u4e00-\u9fff]+)$', s)
    if m:
        h = _cn2num(m.group(1))
        mn = _cn2num(m.group(2))
        if h is not None and mn is not None:
            n = datetime.now(default)
            return n.replace(hour=h, minute=mn, second=0, microsecond=0)
    m = re.match(r'^([\u4e00-\u9fff]+)点半$', s)
    if m:
        h = _cn2num(m.group(1))
        if h is not None:
            n = datetime.now(default)
            return n.replace(hour=h, minute=30, second=0, microsecond=0)
    m = re.match(r'^([\u4e00-\u9fff]+)点', s)
    if m:
        h = _cn2num(m.group(1))
        if h is not None:
            n = datetime.now(default)
            return n.replace(hour=h, minute=0, second=0, microsecond=0)
    return None


def get_epg_for_channel(api, channel_id, start_time=None, end_time=None):
    now_utc = datetime.now(timezone.utc)
    start_dt = parse_time(start_time) if start_time else (now_utc - timedelta(days=14))
    if start_dt is None:
        start_dt = now_utc - timedelta(days=14)
    end_dt = parse_time(end_time) if end_time else (now_utc + timedelta(days=7))
    if end_dt is None:
        end_dt = now_utc + timedelta(days=7)

    response = api.pvr_get_broadcasts(
        channel_id,
        ['title', 'starttime', 'endtime'],
    )
    if not response or 'result' not in response:
        return []
    broadcasts = response['result'].get('broadcasts', [])

    filtered = []
    for b in broadcasts:
        start = parse_time(b.get('starttime', ''))
        end = parse_time(b.get('endtime', ''))
        if start and end and start < end_dt and end > start_dt:
            filtered.append(b)
    return filtered


def find_program_at(epg, target_dt):
    for program in epg:
        start = parse_time(program.get('starttime', ''))
        end = parse_time(program.get('endtime', ''))
        if start and end and start <= target_dt < end:
            return program
    return None


def find_program_in_epg(epg, date_str, time_str):
    local_tz = LOCAL_TZ
    target_date = parse_time(date_str, default_tz='local') if date_str else None
    target_time = parse_time(time_str, default_tz='local') if time_str else None
    if target_date is None and target_time is None:
        return None
    if target_date and target_time:
        target_dt = target_date.astimezone(local_tz).replace(
            hour=target_time.hour, minute=target_time.minute,
            second=target_time.second, microsecond=0)
    elif target_date:
        target_dt = target_date.astimezone(local_tz)
    else:
        today_local = datetime.now(local_tz)
        target_dt = today_local.replace(
            hour=target_time.hour, minute=target_time.minute,
            second=target_time.second, microsecond=0)
    target_utc = target_dt.astimezone(timezone.utc)
    target_local_day = target_dt.date()
    for program in epg:
        start = parse_time(program.get('starttime', ''))
        end = parse_time(program.get('endtime', ''))
        if not (start and end and start <= target_utc < end):
            continue
        if target_date is not None:
            if start.astimezone(local_tz).date() != target_local_day:
                continue
        return program
    return None


def _resolve_epg_source(m3u_text=None, epg_param=None):
    """Resolve EPG source: CLI --epg > config iptv.epg > m3u x-tvg-url.

    Returns an http(s) URL or local file path, or None."""
    if epg_param:
        return epg_param
    configured = load_config().get('iptv', {}).get('epg', '')
    if configured:
        return configured
    if m3u_text:
        url = get_x_tvg_url(m3u_text)
        if url:
            return url
    return None


def _fetch_m3u_source(m3u):
    """Fetch m3u text; prints error and returns None on failure."""
    try:
        return m3u_read_text(m3u)
    except Exception as e:
        print(f'Failed to fetch m3u: {m3u} ({e})')
        return None


def _resolve_epg_or_hint(m3u_text, epg):
    """Resolve EPG source; prints hint and returns None when missing."""
    epg_url = _resolve_epg_source(m3u_text, epg)
    if not epg_url:
        print(epg_config_hint())
    return epg_url


def _parse_epg_source(epg_url):
    """Parse XMLTV; prints error and returns None on failure."""
    try:
        return parse_xmltv(epg_url)
    except Exception as e:
        print(f'Failed to parse EPG: {epg_url} ({e})')
        return None


def _find_pvr_channel(api, channel, suggest=True):
    """Resolve a PVR channel by name; prints error and returns None on failure."""
    channels = get_all_channels(api)
    if not channels:
        return None
    target = find_channel_by_name(channels, channel)
    if not target:
        print(f"Channel '{channel}' not found.")
        if suggest:
            print("Did you mean one of:")
            for ch in channels[:8]:
                print(f"  - {ch.get('label', '?')}")
        return None
    return target


def _xmltv_candidates(label, tvg_id, epg_channels):
    """Ordered candidate channel ids for a channel in an XMLTV index.

    Starts from tvg_id (if any) then label, then adds every XMLTV channel
    whose id/display-name matches either (order-preserving, unique).
    """
    candidates = []

    def add(cid):
        if cid and cid not in candidates:
            candidates.append(cid)

    if tvg_id:
        add(tvg_id)
        for epg_label, epg_name in epg_channels.items():
            if epg_name == tvg_id or epg_label == tvg_id:
                add(epg_label)
    add(label)
    for epg_label, epg_name in epg_channels.items():
        if epg_label == label or (epg_name and (
                epg_name == label or epg_name == tvg_id or
                label in epg_name or (tvg_id and tvg_id in epg_name))):
            add(epg_label)
    return candidates


def _play_catchup_from_http(player, channel, date_str, time_str, m3u, epg=None, local_tz=None):
    """Play catch-up using HTTP m3u + HTTP EPG. Routes playback through player."""
    m3u_text = _fetch_m3u_source(m3u)
    if m3u_text is None:
        return False
    print(f'M3U: {m3u}')

    epg_url = _resolve_epg_or_hint(m3u_text, epg)
    if not epg_url:
        return False
    print(f'EPG: {epg_url}')

    entries = parse_m3u(m3u_text)
    m3u_entry = m3u_find_channel(entries, channel)
    if not m3u_entry:
        print(f"Channel '{channel}' not in m3u.")
        return False
    label = m3u_entry.get('label') or m3u_entry.get('tvg_name') or channel
    tvg_id = m3u_entry.get('tvg_id') or ''
    print(f"M3U channel: {label}  (tvg-id={tvg_id})")
    if not m3u_entry.get('catchup_source'):
        print(f"Channel '{channel}' has no catchup-source in m3u.")
        return False

    parsed = _parse_epg_source(epg_url)
    if parsed is None:
        return False
    epg_channels, programs = parsed
    print(f'EPG channels: {len(epg_channels)}  programs: {len(programs)}')

    target_local_dt = None
    if date_str or time_str:
        if date_str and time_str:
            d = parse_time(date_str, default_tz='local')
            t = parse_time(time_str, default_tz='local')
            if d is None:
                print(f'Could not parse date: {date_str!r}')
                return False
            if t is None:
                print(f'Could not parse time: {time_str!r}')
                return False
            target_local_dt = d.astimezone(local_tz).replace(
                hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
        elif date_str:
            d = parse_time(date_str, default_tz='local')
            if d is None:
                print(f'Could not parse date: {date_str!r}')
                return False
            target_local_dt = d.astimezone(local_tz)
        else:
            t = parse_time(time_str, default_tz='local')
            if t is None:
                print(f'Could not parse time: {time_str!r}')
                return False
            target_local_dt = datetime.now(local_tz).replace(
                hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
    if not target_local_dt:
        print('Need --date and/or --time.')
        return False

    candidates = _xmltv_candidates(label, tvg_id, epg_channels)
    program = None
    for cid in candidates:
        if not cid:
            continue
        program = find_program_in_xmltv(programs, cid, target_local_dt)
        if program:
            break
    if not program:
        print(f"No programme on '{channel}' at {target_local_dt}.")
        return False

    start_utc = program['start_utc']
    end_utc = program['end_utc']
    url = build_catchup_url(m3u_entry['catchup_source'], start_utc, end_utc,
                            local_tz=local_tz,
                            catchup_id=m3u_entry.get('catchup_days'))
    if not url:
        print('Could not build catchup URL.')
        return False

    local_start = start_utc.astimezone(local_tz)
    local_end = end_utc.astimezone(local_tz)
    print(f"\nProgramme: {program['title']}")
    print(f"Time: {local_start:%Y-%m-%d %H:%M} - {local_end:%H:%M} (local)")
    print(f"Catchup URL: {url}")

    if player:
        player.play_url(url)
    return True


def play_catchup(player, channel, date_str, time_str, m3u=None, epg=None):
    """Play catch-up TV. Routes through player abstraction."""
    local_tz = LOCAL_TZ

    if m3u and re.match(r'^https?://', m3u, re.IGNORECASE):
        return _play_catchup_from_http(player, channel, date_str, time_str, m3u, epg, local_tz)

    api = resolve_kodi_api(player)

    if api:
        target_channel = _find_pvr_channel(api, channel, suggest=False)
        if not target_channel:
            return False
        channel_id = target_channel['channelid']
        print(f"Found channel: {target_channel.get('label', 'Unknown')} (ID: {channel_id})")

        pvr_epg_data = get_epg_for_channel(api, channel_id)
        if not pvr_epg_data:
            patch_m3u = m3u or load_config().get('iptv', {}).get('m3u', '')
            if not patch_m3u:
                print(f"No EPG data available for channel '{channel}'.")
                print("Catch-up patch needs an m3u: pass --m3u or set iptv.m3u in config.")
                return False
            print("PVR EPG unavailable - falling back to m3u/XMLTV catch-up patch...")
            return _play_catchup_from_http(player, channel, date_str, time_str, patch_m3u, epg, local_tz)
        program = find_program_in_epg(pvr_epg_data, date_str, time_str)
        if not program:
            print(f"No program found for channel '{channel}' at {date_str} {time_str}.")
            return False

        m3u_source_label = None
        m3u_text = None
        if m3u:
            try:
                m3u_text = m3u_read_text(m3u)
                m3u_source_label = m3u
            except Exception as e:
                print(f"M3U not readable: {m3u} ({e})")
                return False
        else:
            broadcast_id = program.get('broadcastid')
            if not broadcast_id:
                print("Program has no broadcastid; cannot play catch-up.")
                return False
            print(f"\nPlaying catch-up: {program.get('title', 'Unknown')}")
            print(f"Broadcast ID: {broadcast_id}")
            item = {'broadcastid': broadcast_id}
            if player:
                player.play_item(item)
            else:
                api.player_open_item(item)
            return True

        entries = parse_m3u(m3u_text)
        m3u_entry = m3u_find_channel(entries, target_channel.get('label', channel))
        if not m3u_entry or not m3u_entry.get('catchup_source'):
            print(f"Channel '{channel}' has no catchup-source in {m3u_source_label}.")
            return False
        template = m3u_entry['catchup_source']
        start_utc = parse_time(program.get('starttime', ''))
        end_utc = parse_time(program.get('endtime', ''))
        if not (start_utc and end_utc):
            print("Program has no valid start/end time.")
            return False
        url = build_catchup_url(template, start_utc, end_utc, local_tz=local_tz,
                                catchup_id=m3u_entry.get('catchup_days'))
        if not url:
            print("Could not build catchup URL.")
            return False
        print(f"\nPlaying catch-up: {program.get('title', 'Unknown')}")
        print(f"Catchup URL: {url}")
        if player:
            player.play_url(url)
        else:
            api.player_open_item({'file': url})
        return True
    else:
        print("No KODI available for PVR-based catch-up. Use --m3u instead.")
        return False


def show_current_program(player, channel):
    """Play a live TV channel and show current EPG info."""
    api = resolve_kodi_api(player)

    if api:
        target_channel = _find_pvr_channel(api, channel)
        if not target_channel:
            return False
        channel_id = target_channel['channelid']
        label = target_channel.get('label', 'Unknown')
        print(f"Found channel: {label} (ID: {channel_id})")
        epg = get_epg_for_channel(api, channel_id)
        now_utc = datetime.now(timezone.utc)
        if not epg:
            print("No EPG data available.")
        else:
            current = find_program_at(epg, now_utc)
            if current:
                title = current.get('title', 'Unknown')
                print(f"Current program: {title}")
                st = parse_time(current.get('starttime', ''))
                et = parse_time(current.get('endtime', ''))
                if st and et:
                    local_tz = LOCAL_TZ
                    st_local = st.astimezone(local_tz).strftime('%Y-%m-%d %H:%M')
                    et_local = et.astimezone(local_tz).strftime('%H:%M')
                    print(f"  Time: {st_local} - {et_local} (local)")
            else:
                print("No current program information (channel may be offline).")
        print(f"\nTuning to: {label}")
        item = {'channelid': channel_id}
        if player:
            player.play_item(item)
        else:
            api.player_open_item(item)
        return True
    else:
        print("No KODI available. For local mode, use --action epg with m3u URL.")
        return False


def _show_all_epg_kodi(api):
    """Show currently-playing program for ALL PVR channels (KODI mode)."""
    local_tz = LOCAL_TZ
    now_local = datetime.now(local_tz)
    now_utc = datetime.now(timezone.utc)

    channels = get_all_channels(api)
    if not channels:
        print("No channels found.")
        return False

    print(f"Current programs ({now_local.strftime('%Y-%m-%d %H:%M')}):")
    print()

    for ch in channels:
        label = ch.get('label', '?')
        channel_id = ch['channelid']
        epg = get_epg_for_channel(api, channel_id)
        if not epg:
            continue
        current = find_program_at(epg, now_utc)
        if not current:
            continue
        st = parse_time(current.get('starttime', ''))
        et = parse_time(current.get('endtime', ''))
        if st and et:
            s = st.astimezone(local_tz).strftime('%H:%M')
            e = et.astimezone(local_tz).strftime('%H:%M')
            print(f"  {label}: {current.get('title', '?')}  ({s}-{e})")
        else:
            print(f"  {label}: {current.get('title', '?')}")

    return True


def show_epg(player=None, channel=None, date_str='', time_str='', m3u=None, epg=None):
    """Browse EPG. Supports KODI PVR EPG and m3u+XMLTV (URL or local file)."""
    if m3u:
        if channel:
            return _show_epg_from_http(player, channel, date_str, time_str, m3u, epg)
        else:
            return _show_all_epg_from_http(player, m3u, epg)

    api = resolve_kodi_api(player)

    if not api:
        print("KODI API required for PVR EPG. Use --m3u for m3u/EPG lookup.")
        return False

    if channel is None:
        return _show_all_epg_kodi(api)

    target_channel = _find_pvr_channel(api, channel)
    if not target_channel:
        return False
    channel_id = target_channel['channelid']
    label = target_channel.get('label', 'Unknown')
    print(f"\nChannel: {label} (ID: {channel_id})")

    pvr_epg_data = get_epg_for_channel(api, channel_id)
    if not pvr_epg_data:
        patch_m3u = m3u or load_config().get('iptv', {}).get('m3u', '')
        if not patch_m3u:
            print("No EPG data available.")
            print("EPG patch needs an m3u: pass --m3u or set iptv.m3u in config.")
            return False
        print("PVR EPG unavailable - falling back to m3u/XMLTV EPG patch...")
        return _show_epg_from_http(player, channel, date_str, time_str, patch_m3u, epg)

    local_tz = LOCAL_TZ
    now_local = datetime.now(local_tz)

    if date_str and time_str:
        target = parse_time(date_str, default_tz='local')
        if target is None:
            print(f"Invalid date: {date_str}")
            return False
        target = target.astimezone(local_tz)
        t = parse_time(time_str, default_tz='local')
        if t is None:
            print(f"Invalid time: {time_str}")
            return False
        target = target.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        program = find_program_in_epg(pvr_epg_data, date_str, time_str)
        print(f"EPG at {target:%Y-%m-%d %H:%M} (local):")
        if program:
            _print_program(program, local_tz)
        else:
            print("  (no programme at this time)")
        return True

    if date_str:
        day = parse_time(date_str, default_tz='local')
        if day is None:
            print(f"Invalid date: {date_str}")
            return False
        day = day.astimezone(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day + timedelta(days=1)
        day_utc_start = day.astimezone(timezone.utc)
        day_utc_end = day_end.astimezone(timezone.utc)
        day_progs = [p for p in pvr_epg_data if _prog_overlaps(p, day_utc_start, day_utc_end)]
        if not day_progs:
            print(f"No EPG for {day:%Y-%m-%d}.")
            return True
        print(f"EPG for {day:%Y-%m-%d} (local):")
        day_progs.sort(key=lambda p: parse_time(p.get('starttime', '')) or datetime.min)
        for p in day_progs:
            _print_program(p, local_tz)
        return True

    window = timedelta(hours=3)
    win_utc_start = now_local.astimezone(timezone.utc) - window
    win_utc_end = now_local.astimezone(timezone.utc) + window
    current = find_program_at(pvr_epg_data, now_local.astimezone(timezone.utc))
    nearby = [p for p in pvr_epg_data if _prog_overlaps(p, win_utc_start, win_utc_end)]
    if not nearby:
        print("No EPG available around current time.")
        return True
    nearby.sort(key=lambda p: parse_time(p.get('starttime', '')) or datetime.min)
    print(f"EPG around {now_local:%Y-%m-%d %H:%M} (local, +/-{window.seconds//3600}h):")
    for p in nearby:
        prefix = " > " if current and p.get('broadcastid') == current.get('broadcastid') else "   "
        _print_program(p, local_tz, prefix=prefix)
    return True


def _show_epg_from_http(player, channel, date_str, time_str, m3u, epg=None):
    """Browse EPG from HTTP m3u + XMLTV (no KODI needed)."""
    m3u_text = _fetch_m3u_source(m3u)
    if m3u_text is None:
        return False

    entries = parse_m3u(m3u_text)
    m3u_entry = m3u_find_channel(entries, channel)
    if not m3u_entry:
        print(f"Channel '{channel}' not in m3u.")
        return False
    label = m3u_entry.get('label') or m3u_entry.get('tvg_name') or channel
    tvg_id = m3u_entry.get('tvg_id') or ''

    epg_url = _resolve_epg_or_hint(m3u_text, epg)
    if not epg_url:
        return False

    parsed = _parse_epg_source(epg_url)
    if parsed is None:
        return False
    epg_channels, programs = parsed

    local_tz = LOCAL_TZ
    candidates = _xmltv_candidates(label, tvg_id, epg_channels)

    channel_progs = []
    for cid in candidates:
        if not cid:
            continue
        channel_progs.extend([p for p in programs if p['channel'] == cid])
    channel_progs.sort(key=lambda p: p['start_utc'])

    if not channel_progs:
        print(f"No EPG for '{label}'.")
        return True

    print(f"\nChannel: {label}")
    now_local = datetime.now(local_tz)

    if date_str and time_str:
        d = parse_time(date_str, default_tz='local')
        t = parse_time(time_str, default_tz='local')
        if d and t:
            target = d.astimezone(local_tz).replace(
                hour=t.hour, minute=t.minute, second=0, microsecond=0)
            target_utc = target.astimezone(timezone.utc)
            for p in channel_progs:
                if p['start_utc'] <= target_utc < p['end_utc']:
                    print(f"  {p['start_utc'].astimezone(local_tz).strftime('%H:%M')}-"
                          f"{p['end_utc'].astimezone(local_tz).strftime('%H:%M')}  {p['title']}")
                    return True
            print(f"  (no programme at {target})")
        return True

    if date_str:
        day = parse_time(date_str, default_tz='local')
        if day:
            day = day.astimezone(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day + timedelta(days=1)
            day_progs = [p for p in channel_progs
                         if p['start_utc'] < day_end.astimezone(timezone.utc)
                         and p['end_utc'] > day.astimezone(timezone.utc)]
            if day_progs:
                print(f"EPG for {day:%Y-%m-%d}:")
                for p in day_progs:
                    s = p['start_utc'].astimezone(local_tz).strftime('%H:%M')
                    e = p['end_utc'].astimezone(local_tz).strftime('%H:%M')
                    print(f"  {s}-{e}  {p['title']}")
            else:
                print(f"No EPG for {day:%Y-%m-%d}.")
        return True

    window = timedelta(hours=3)
    win_utc_start = now_local.astimezone(timezone.utc) - window
    win_utc_end = now_local.astimezone(timezone.utc) + window
    nearby = [p for p in channel_progs
              if p['start_utc'] < win_utc_end and p['end_utc'] > win_utc_start]
    if not nearby:
        print(f"No EPG around current time.")
        return True
    nearby.sort(key=lambda p: p['start_utc'])
    print(f"EPG around {now_local:%Y-%m-%d %H:%M} (local, +/-{window.seconds//3600}h):")
    for p in nearby:
        s = p['start_utc'].astimezone(local_tz).strftime('%H:%M')
        e = p['end_utc'].astimezone(local_tz).strftime('%H:%M')
        mark = " > " if p['start_utc'] <= now_local.astimezone(timezone.utc) < p['end_utc'] else "   "
        print(f"  {mark}{s}-{e}  {p['title']}")
    return True


def _show_all_epg_from_http(player, m3u, epg=None):
    """Show currently-playing program for ALL channels in the m3u (no KODI needed)."""
    m3u_text = _fetch_m3u_source(m3u)
    if m3u_text is None:
        return False

    entries = parse_m3u(m3u_text)
    if not entries:
        print("No channels found in m3u.")
        return False

    epg_url = _resolve_epg_or_hint(m3u_text, epg)
    if not epg_url:
        return False

    parsed = _parse_epg_source(epg_url)
    if parsed is None:
        return False
    epg_channels, programs = parsed

    local_tz = LOCAL_TZ
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(local_tz)

    print(f"Current programs ({now_local.strftime('%Y-%m-%d %H:%M')}):")
    print()

    for entry in entries:
        label = entry.get('label') or entry.get('tvg_name') or '?'
        tvg_id = entry.get('tvg_id') or ''

        candidates = _xmltv_candidates(label, tvg_id, epg_channels)

        found = None
        for cid in candidates:
            if not cid:
                continue
            for p in programs:
                if p['channel'] != cid:
                    continue
                if p['start_utc'] <= now_utc < p['end_utc']:
                    found = p
                    break
            if found:
                break

        if not found:
            continue
        s = found['start_utc'].astimezone(local_tz).strftime('%H:%M')
        e = found['end_utc'].astimezone(local_tz).strftime('%H:%M')
        print(f"  {label}: {found['title']}  ({s}-{e})")

    return True


def _print_program(program, local_tz, prefix="   "):
    st = parse_time(program.get('starttime', ''))
    et = parse_time(program.get('endtime', ''))
    title = program.get('title', 'Unknown')
    if st and et:
        s = st.astimezone(local_tz).strftime('%H:%M')
        e = et.astimezone(local_tz).strftime('%H:%M')
        print(f"  {prefix}{s}-{e}  {title}")
    else:
        print(f"  {prefix}???-???  {title}")


def _prog_overlaps(program, utc_start, utc_end):
    st = parse_time(program.get('starttime', ''))
    et = parse_time(program.get('endtime', ''))
    if not (st and et):
        return False
    return st < utc_end and et > utc_start
