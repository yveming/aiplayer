#!/usr/bin/env python3
"""
PVR channel browsing, EPG lookup, and catch-up TV.
Supports Player abstraction for KODI and local mpv playback.
"""

import argparse
import json
import sys
import re
import os
from datetime import datetime, timedelta, timezone

from aiplayer.kodi_api import KodiAPI
from aiplayer.m3u_catchup import parse_m3u, find_channel as m3u_find_channel, build_catchup_url, discover_m3u
from aiplayer.m3u_catchup import (parse_xmltv, get_x_tvg_url, find_program_in_xmltv,
                         _read_text as m3u_read_text)
from aiplayer.player import Player, PlayerMode


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
    local_tz = timezone(timedelta(hours=8))
    default = timezone.utc if default_tz == 'utc' else local_tz
    s = time_str.strip()
    sl = s.lower()

    if sl in ('now', '鐜板湪', '褰撳墠'):
        return datetime.now(default)
    if sl in ('today', '浠婂ぉ'):
        return datetime.now(default).replace(hour=0, minute=0, second=0, microsecond=0)
    if sl in ('yesterday', '鏄ㄥぉ'):
        return (datetime.now(default) - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('tomorrow', '鏄庡ぉ'):
        return (datetime.now(default) + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('day_before_yesterday', '鍓嶅ぉ'):
        return (datetime.now(default) - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0)
    if sl in ('day_after_tomorrow', '鍚庡ぉ'):
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

    # Chinese time: '8点, '鍗佺偣', '鍗佺偣涓夊崄分, '8点半'
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
    local_tz = timezone(timedelta(hours=8))
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


def _play_catchup_from_http(player, channel, date_str, time_str, m3u_url, local_tz):
    """Play catch-up using HTTP m3u + HTTP EPG. Routes playback through player."""
    try:
        m3u_text = m3u_read_text(m3u_url)
    except Exception as e:
        print(f'Failed to fetch m3u: {m3u_url} ({e})')
        return False
    print(f'M3U: {m3u_url}')

    epg_url = get_x_tvg_url(m3u_text)
    if not epg_url:
        from urllib.parse import urljoin
        base = m3u_url.rsplit('/', 1)[0] + '/'
        for candidate in ('iptv-epg.xml.gz', 'iptv-epg.xml', 'epg.xml.gz', 'epg.xml'):
            guess = urljoin(base, candidate)
            try:
                m3u_read_text(guess)
                epg_url = guess
                break
            except Exception:
                continue
    if not epg_url:
        print('No EPG URL found.')
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

    try:
        epg_channels, programs = parse_xmltv(epg_url)
    except Exception as e:
        print(f'Failed to parse EPG: {epg_url} ({e})')
        return False
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

    candidates = [tvg_id, label] if tvg_id else [label]
    for epg_label, epg_name in epg_channels.items():
        if (epg_label == label or
                (epg_name and (epg_name == label or epg_name == tvg_id or
                               label in epg_name or tvg_id in epg_name))):
            if epg_label not in candidates:
                candidates.append(epg_label)
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


def _play_live_channel(player, channel_url, channel_label):
    """Play a live TV channel URL through the player abstraction."""
    print(f"\nTuning to: {channel_label}")
    print(f"Stream URL: {channel_url}")
    if player:
        player.play_url(channel_url)
    return True


def play_catchup(player, channel, date_str, time_str, m3u_path=None, m3u_url=None):
    """Play catch-up TV. Routes through player abstraction."""
    local_tz = timezone(timedelta(hours=8))

    if m3u_url:
        return _play_catchup_from_http(player, channel, date_str, time_str, m3u_url, local_tz)

    api = None
    if isinstance(player, Player):
        if player.kodi:
            api = player.kodi
    elif isinstance(player, KodiAPI):
        api = player

    if api:
        channels = get_all_channels(api)
        if not channels:
            return False
        target_channel = find_channel_by_name(channels, channel)
        if not target_channel:
            print(f"Channel '{channel}' not found.")
            return False
        channel_id = target_channel['channelid']
        print(f"Found channel: {target_channel.get('label', 'Unknown')} (ID: {channel_id})")

        epg = get_epg_for_channel(api, channel_id)
        if not epg:
            print(f"No EPG data available for channel '{channel}'.")
            return False
        program = find_program_in_epg(epg, date_str, time_str)
        if not program:
            print(f"No program found for channel '{channel}' at {date_str} {time_str}.")
            return False

        m3u_source_label = None
        m3u_text = None
        if m3u_path:
            try:
                with open(m3u_path, 'r', encoding='utf-8') as f:
                    m3u_text = f.read()
                m3u_source_label = m3u_path
            except OSError as e:
                print(f"M3U file not readable: {m3u_path} ({e})")
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
        print("No KODI available for PVR-based catch-up. Use --m3u-url instead.")
        return False


def show_current_program(player, channel):
    """Play a live TV channel and show current EPG info."""
    api = None
    if isinstance(player, Player):
        if player.kodi:
            api = player.kodi
    elif isinstance(player, KodiAPI):
        api = player

    if api:
        channels = get_all_channels(api)
        if not channels:
            return False
        target_channel = find_channel_by_name(channels, channel)
        if not target_channel:
            print(f"Channel '{channel}' not found.")
            print("Did you mean one of:")
            for ch in channels[:8]:
                print(f"  - {ch.get('label', '?')}")
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
                    local_tz = timezone(timedelta(hours=8))
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
    local_tz = timezone(timedelta(hours=8))
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


def show_epg(player=None, channel=None, date_str='', time_str='', m3u_url=None):
    """Browse EPG. Supports both KODI PVR EPG and HTTP m3u+XMLTV EPG."""
    if m3u_url:
        if channel:
            return _show_epg_from_http(player, channel, date_str, time_str, m3u_url)
        else:
            return _show_all_epg_from_http(player, m3u_url)

    api = None
    if isinstance(player, Player):
        if player.kodi:
            api = player.kodi
    elif isinstance(player, KodiAPI):
        api = player

    if not api:
        print("KODI API required for PVR EPG. Use --m3u-url for HTTP EPG.")
        return False

    if channel is None:
        return _show_all_epg_kodi(api)

    channels = get_all_channels(api)
    if not channels:
        return False
    target_channel = find_channel_by_name(channels, channel)
    if not target_channel:
        print(f"Channel '{channel}' not found.")
        print("Did you mean one of:")
        for ch in channels[:8]:
            print(f"  - {ch.get('label', '?')}")
        return False
    channel_id = target_channel['channelid']
    label = target_channel.get('label', 'Unknown')
    print(f"\nChannel: {label} (ID: {channel_id})")

    epg = get_epg_for_channel(api, channel_id)
    if not epg:
        print("No EPG data available.")
        return False

    local_tz = timezone(timedelta(hours=8))
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
        program = find_program_in_epg(epg, date_str, time_str)
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
        day_progs = [p for p in epg if _prog_overlaps(p, day_utc_start, day_utc_end)]
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
    current = find_program_at(epg, now_local.astimezone(timezone.utc))
    nearby = [p for p in epg if _prog_overlaps(p, win_utc_start, win_utc_end)]
    if not nearby:
        print("No EPG available around current time.")
        return True
    nearby.sort(key=lambda p: parse_time(p.get('starttime', '')) or datetime.min)
    print(f"EPG around {now_local:%Y-%m-%d %H:%M} (local, +/-{window.seconds//3600}h):")
    for p in nearby:
        prefix = " > " if current and p.get('broadcastid') == current.get('broadcastid') else "   "
        _print_program(p, local_tz, prefix=prefix)
    return True


def _show_epg_from_http(player, channel, date_str, time_str, m3u_url):
    """Browse EPG from HTTP m3u + XMLTV (no KODI needed)."""
    try:
        m3u_text = m3u_read_text(m3u_url)
    except Exception as e:
        print(f'Failed to fetch m3u: {m3u_url} ({e})')
        return False

    entries = parse_m3u(m3u_text)
    m3u_entry = m3u_find_channel(entries, channel)
    if not m3u_entry:
        print(f"Channel '{channel}' not in m3u.")
        return False
    label = m3u_entry.get('label') or m3u_entry.get('tvg_name') or channel
    tvg_id = m3u_entry.get('tvg_id') or ''

    epg_url = get_x_tvg_url(m3u_text)
    if not epg_url:
        from urllib.parse import urljoin
        base = m3u_url.rsplit('/', 1)[0] + '/'
        for candidate in ('iptv-epg.xml.gz', 'iptv-epg.xml', 'epg.xml.gz', 'epg.xml'):
            guess = urljoin(base, candidate)
            try:
                m3u_read_text(guess)
                epg_url = guess
                break
            except Exception:
                continue
    if not epg_url:
        print('No EPG URL found.')
        return False

    try:
        epg_channels, programs = parse_xmltv(epg_url)
    except Exception as e:
        print(f'Failed to parse EPG: {e}')
        return False

    local_tz = timezone(timedelta(hours=8))
    candidates = [tvg_id, label] if tvg_id else [label]
    for epg_label, epg_name in epg_channels.items():
        if (epg_label == label or
                (epg_name and (epg_name == label or label in epg_name))):
            if epg_label not in candidates:
                candidates.append(epg_label)

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



def _show_all_epg_from_http(player, m3u_url):
    """Show currently-playing program for ALL channels in the m3u (no KODI needed)."""
    import urllib.request
    from datetime import datetime, timezone, timedelta

    try:
        m3u_text = m3u_read_text(m3u_url)
    except Exception as e:
        print(f'Failed to fetch m3u: {m3u_url} ({e})')
        return False

    entries = parse_m3u(m3u_text)
    if not entries:
        print("No channels found in m3u.")
        return False

    epg_url = get_x_tvg_url(m3u_text)
    if not epg_url:
        from urllib.parse import urljoin
        base = m3u_url.rsplit('/', 1)[0] + '/'
        for candidate in ('iptv-epg.xml.gz', 'iptv-epg.xml', 'epg.xml.gz', 'epg.xml'):
            guess = urljoin(base, candidate)
            try:
                m3u_read_text(guess)
                epg_url = guess
                break
            except Exception:
                continue
    if not epg_url:
        print('No EPG URL found.')
        return False

    try:
        epg_channels, programs = parse_xmltv(epg_url)
    except Exception as e:
        print(f'Failed to parse EPG: {e}')
        return False

    local_tz = timezone(timedelta(hours=8))
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(local_tz)

    print(f"Current programs ({now_local.strftime('%Y-%m-%d %H:%M')}):")
    print()

    for entry in entries:
        label = entry.get('label') or entry.get('tvg_name') or '?'
        tvg_id = entry.get('tvg_id') or ''

        candidates = []
        if tvg_id:
            candidates.append(tvg_id)
            for epg_label, epg_name in epg_channels.items():
                if epg_name == tvg_id or epg_label == tvg_id:
                    if epg_label not in candidates:
                        candidates.append(epg_label)
        candidates.append(label)
        for epg_label, epg_name in epg_channels.items():
            if epg_name == label or epg_label == label:
                if epg_label not in candidates:
                    candidates.append(epg_label)

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


def main():
    parser = argparse.ArgumentParser(
        description='TV channel browsing, EPG lookup, and catch-up',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  ./pvr_epg.py --action channels\n'
            '  ./pvr_epg.py --action epg --channel "CCTV1"\n'
            '  ./pvr_epg.py --action play --channel "CCTV1"\n'
            '  ./pvr_epg.py --action catchup --channel "CCTV1" --date yesterday --time 21:00\n'
            '  ./pvr_epg.py --action catchup --channel "CCTV1" --date yesterday --time 21:00 --m3u-url http://.../iptv.m3u\n'
            '  # Local mode (no KODI):\n'
            '  ./pvr_epg.py --action epg --channel "CCTV1" --m3u-url http://.../iptv.m3u --local\n'
            '  ./pvr_epg.py --action play --channel "CCTV1" --m3u-url http://.../iptv.m3u --local\n'
        ),
    )
    parser.add_argument('--host', default='127.0.0.1', help='KODI host IP')
    parser.add_argument('--port', type=int, default=9090, help='KODI port')
    parser.add_argument('--username', default='', help='KODI username')
    parser.add_argument('--password', default='', help='KODI password')
    parser.add_argument('--protocol', choices=['tcp', 'http', 'auto'], default='auto', help='Connection protocol')
    parser.add_argument('--action', choices=['channels', 'epg', 'catchup', 'play'], required=True,
                        help='Action to perform')
    parser.add_argument('--channel', default='', help='Channel name')
    parser.add_argument('--date', default='', help='Date (yesterday/today/YYYY-MM-DD or now)')
    parser.add_argument('--time', default='', help='Time (HH:MM or HH:MM:SS)')
    parser.add_argument('--m3u', default='', help='Path to local m3u file')
    parser.add_argument('--m3u-url', default='', help='URL to IPTV m3u (HTTP)')
    parser.add_argument('--local', action='store_true', help='Use local mpv mode (no KODI)')

    args = parser.parse_args()

    player = None
    if args.local:
        player = Player(mode=PlayerMode.LOCAL)
        print("Using local mpv player (no KODI)")
    else:
        api = KodiAPI(args.host, args.port, args.username, args.password, protocol=args.protocol)
        version = api.get_version()
        if not version or 'result' not in version:
            print(f"Cannot connect to KODI at {args.host}:{args.port}")

            if args.m3u_url:
                print("Falling back to local mode with m3u URL...")
                player = Player(mode=PlayerMode.LOCAL)
            else:
                sys.exit(1)
        else:
            print(f"Connected to KODI v{version['result'].get('version', 'unknown')}")
            player = api

    if args.action == 'channels':
        if args.m3u_url:
            entries = m3u_find_channel(parse_m3u(m3u_read_text(args.m3u_url)), '')  # just to check
            from aiplayer.m3u_catchup import parse_m3u as _parse_m3u
            text = m3u_read_text(args.m3u_url)
            entries = _parse_m3u(text)
            print(f"\nFound {len(entries)} channels in m3u:")
            for i, e in enumerate(entries, 1):
                name = e.get('label') or e.get('tvg_name') or '?'
                print(f"{i}. {name}")
            sys.exit(0)
        api = player.kodi if isinstance(player, Player) else player
        channels = get_all_channels(api)
        if channels:
            print(f"\nFound {len(channels)} channels:")
            for i, ch in enumerate(channels, 1):
                print(f"{i}. {ch.get('label', 'Unknown')} (ID: {ch.get('channelid', 'N/A')}) [{ch.get('group', 'Unknown')}]")
        else:
            print("No channels found.")
        sys.exit(0 if channels else 1)

    elif args.action == 'epg':
        if not args.channel:
            print("Channel name required for EPG lookup.")
            sys.exit(1)
        if args.m3u_url:
            success = _show_epg_from_http(player, args.channel, args.date, args.time, args.m3u_url)
        else:
            success = show_epg(player, args.channel, args.date, args.time)
        sys.exit(0 if success else 1)

    elif args.action == 'play':
        if not args.channel:
            print("Channel name required to play.")
            sys.exit(1)
        if args.m3u_url:
            api = player.kodi if isinstance(player, Player) and player.kodi else None
            if not api:
                from aiplayer.m3u_catchup import parse_m3u as _parse_m3u
                text = m3u_read_text(args.m3u_url)
                entries = _parse_m3u(text)
                m3u_entry = m3u_find_channel(entries, args.channel)
                if m3u_entry:
                    url = m3u_entry.get('stream_url', '')
                    if url:
                        success = _play_live_channel(player, url, args.channel)
                        sys.exit(0 if success else 1)
                print(f"Channel '{args.channel}' not in m3u.")
                sys.exit(1)
            success = show_current_program(player, args.channel)
        else:
            success = show_current_program(player, args.channel)
        sys.exit(0 if success else 1)

    elif args.action == 'catchup':
        if not args.channel or not args.date or not args.time:
            print("Channel, date, and time required for catch-up.")
            sys.exit(1)
        success = play_catchup(player, args.channel, args.date, args.time,
                              m3u_path=args.m3u or None,
                              m3u_url=args.m3u_url or None)
        sys.exit(0 if success else 1)

    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)


if __name__ == '__main__':
    main()
