---
name: aiplayer
description: >
  Control media playback using KODI (via JSON-RPC) or local mpv player.
  Auto-discovers KODI instances or falls back to local directories for movies/TV/music.
  For live TV, uses HTTP m3u/EPG when no KODI is available.
---

# aiplayer - Unified Media Player

## Overview

aiplayer unifies KODI remote control and local mpv playback under one interface:
- **KODI mode**: Full KODI JSON-RPC control (discovery, search, play, PVR/EPG)
- **Local mode**: mpv-based playback with local filesystem search (CIFS/NFS mounts)
- **TV mode**: HTTP m3u + XMLTV EPG for live TV and catch-up (via mpv or KODI)

## Architecture

```
aiplayer.py (entry point, aiplayer/scripts/)
  +-- player.py  (Player abstraction: KODI vs local mpv)
  |     +-- KodiAPI (kodi_api.py)     JSON-RPC to KODI
  |     +-- MpvPlayer (local_player.py)  mpv IPC control
  +-- discover.py  discover KODI or detect local media dirs
  +-- search_play.py  search & play (KODI library + remote/local dirs)
  +-- playback_control.py  pause/resume/skip/volume
  +-- pvr_epg.py  TV channels/EPG/catch-up
  +-- m3u_catchup.py  m3u parser + URL builder + XMLTV EPG
```

All scripts under `aiplayer/scripts/`.

---

## Command Format

```
python aiplayer/scripts/aiplayer.py [connection-flags] <action> [query] [action-flags]
```

---

## How AI Agents Must Use This

1. **If you know the KODI boxes.** Never auto-discover. Always use `--host` with known addresses.
2. **Always use `--host`** for all KODI calls (fast, no discovery).
3. **Use `--local`** only when user says no KODI or the commands don't need a speaker/TV.
4. **Playback control** (pause, skip, volume, stop, status) works in whichever mode the *last play command* used. You must use the same `--host` or `--local` flags.
   - Example: last played via KODI → control commands also need `--host ...`
   - Example: last played via `--local` → control commands need `--local`

---

## Connection Flags (choose ONE group)

### Group A: KODI mode (use known addresses)

```
--host <IP> --port <PORT> --protocol <tcp|http> [--username <USER> --password <PASS>]
```

To list channels and verify connection:
```
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channels
```

### Group B: Local mpv mode (no KODI, files on disk + m3u TV)

```
--local
```

No discovery needed. Media searched from G:\movie, G:\video, G:\music for windows and /mnt/media/{movie,video,music} for Linux . TV requires `--m3u-url`.

### Group C: Auto-discover (DON'T use — slow)

Omitting both `--host` and `--local` triggers SSDP/mDNS. Takes ~5s. Only use once to find KODI address, then switch to Group A.

---

## All Actions

| Action | Description | Requires query? | Local/KODI |
|--------|-------------|-----------------|------------|
| `movie` | Search and play a movie | yes | both |
| `tv` | Search and play a TV episode (S03E04) | yes | both |
| `music` | Search and play music (with `--artist`/`--album`/`--song`) | optional | both |
| `channel` | Play a live TV channel | yes to play; no to list | both |
| `channels` | List all available channels | no | both |
| `epg` | Browse EPG for a channel | yes | both |
| `catchup` | Play catch-up TV | yes | both |
| `pause` | Toggle pause | no | both |
| `play` | Resume playback | no | both |
| `playpause` | Toggle play/pause | no | both |
| `next` | Next track/station | no | both |
| `prev` | Previous track/station | no | both |
| `stop` | Stop playback | no | both |
| `restart` | Restart current track | no | both |
| `volume_up` | Volume +10% | no | both |
| `volume_down` | Volume -10% | no | both |
| `mute` | Toggle mute | no | both |
| `status` | Show current playback info | no | both |
| `nowplaying` | Same as status | no | both |
| `playfile` | Play/replace a file by path | yes (path) | both |
| `enqueue` | Append a file to playlist | yes (path) | both |
| `playfiles` | Clear playlist, play multiple files by path | yes (paths...) | both |

---

## All Command-Line Flags

| Flag | Type | Used with | Description |
|------|------|-----------|-------------|
| `--host` | IP | KODI mode | KODI IP address |
| `--port` | int | `--host` | KODI port (default 9090 or 8080) |
| `--protocol` | tcp/http/auto | `--host` | Connection protocol |
| `--username` | str | `--host` http | HTTP auth username |
| `--password` | str | `--host` http | HTTP auth password |
| `--local` | flag | standalone | Force local mpv mode |
| `--m3u-url` | URL | channel/catchup/channels/epg | HTTP m3u playlist URL |
| `--m3u` | filepath | catchup | Local m3u file path |
| `--artist` | str | music | Artist name filter |
| `--album` | str | music | Album name filter |
| `--song` | str | music | Song name filter |
| `--shuffle` | flag | music | Random playback order |
| `--date` | str | catchup, epg | Date keyword or YYYY-MM-DD |
| `--time` | str | catchup | Time keyword or HH:MM |
| `--debug` | flag | any | Verbose debug output |
| `--mpv-path` | path | --local | mpv executable path |
| `--max-depth` | int | search | Directory recursion depth |
| `--prefer-local` | flag | auto | Prefer local over KODI |

---

## Action Reference (all patterns)

### movie — Search and play movies

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp movie "Avatar"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp movie "阿凡达"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol http --username kodi --password hermes movie "Interstellar"

# local
python aiplayer/scripts/aiplayer.py --local movie "Avatar"
python aiplayer/scripts/aiplayer.py --local movie "阿凡达"
```

Keywords: `放电影`, `电影`, `movie`

### tv — Search and play TV episodes

Query must contain season/episode info (S03E04, 3x04, 第三季第四集).

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp tv "Dark Matter S03E04"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp tv "黑暗物质 第三季第四集"

# local
python aiplayer/scripts/aiplayer.py --local tv "Dark Matter S03E04"
```

Keywords: `放视频`, `放电视`, `视频`, `电视`, `tv`, `episode`

### music — Search and play music

Uses `--artist`, `--album`, `--song` flags (all optional). `--shuffle` for random.

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp music --artist "赵传"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp music --artist "赵传" --album "我是一只小小鸟" --song "我是一只小小鸟" --shuffle

# local
python aiplayer/scripts/aiplayer.py --local music --artist "赵传"
python aiplayer/scripts/aiplayer.py --local music "我是一只小小鸟"
```

Music selection: enter `1`, `1,3,5`, `1-5`, `a`/`all`, `q`.

Keywords: `放音乐`, `音乐`, `music`, `song`

### channel — Live TV

```
# KODI PVR
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channel "CCTV1"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channel "湖南卫视"

# KODI + m3u helper (CoreELEC box catchup broken)
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channel "CCTV1" --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u

# local mpv
python aiplayer/scripts/aiplayer.py --local channel "CCTV1" --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u

# list channels (no query)
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channel
python aiplayer/scripts/aiplayer.py --local channel --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u
```

Keywords: `放电视`, `电视`, `live`, `channel`, `频道`

### channels — List all channels

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp channels

# m3u
python aiplayer/scripts/aiplayer.py --local channels --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u
```

### epg — Browse EPG

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp epg "CCTV1"
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp epg "CCTV1" --date today

# HTTP m3u EPG
python aiplayer/scripts/aiplayer.py --local epg "CCTV1" --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u --date yesterday
```

Keywords: `节目表`, `epg`, `节目单`

### catchup — TV catch-up / 回看

Requires `--date` and `--time`. Date/time accepts Chinese keywords (昨天/前天/八点/八点半).

```
# KODI + m3u (CoreELEC box)
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp catchup "CCTV1" --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u --date yesterday --time 21:00

# Sony TV (broadcastid, no --m3u-url)
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol http --username kodi --password hermes catchup "CCTV1" --date yesterday --time "晚上9点"

# local + m3u
python aiplayer/scripts/aiplayer.py --local catchup "CCTV1" --m3u-url http://192.168.100.2:8000/iptv/iptv.m3u --date 前天 --time "十点"
```

Keywords: `回看`, `电视回看`, `catchup`

### Playback control

Must use same connection flags as last play command.

```
# KODI
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp pause
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp next
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp prev
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp restart
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp stop
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp volume_up
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp volume_down
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp mute
python aiplayer/scripts/aiplayer.py --host <IP> --port <PORT> --protocol tcp status

# local
python aiplayer/scripts/aiplayer.py --local pause
python aiplayer/scripts/aiplayer.py --local next
python aiplayer/scripts/aiplayer.py --local prev
python aiplayer/scripts/aiplayer.py --local stop
python aiplayer/scripts/aiplayer.py --local status
```

Keywords: `暂停`→pause, `继续`/`播放`→play, `下一首`/`下一集`→next, `上一首`/`上一集`→prev, `重来`/`从头开始`→restart, `停止`→stop, `大声点`→volume_up, `小声点`→volume_down, `静音`→mute, `当前播放`/`进度`→status

---

## Ask user for IPTV backend

Example IPTV backend: http://192.168.100.2:8000/iptv/iptv.m3u (52 channels, RTP multicast)

---

## Important Notes

- **Discovery is slow (~5s)**: Never auto-discover. Use known `--host` addresses.
- **Always pass `--host` (or `--local`)**: Every single call needs connection flags.
- **Same flags for control**: Pause/skip/volume/status must use same `--host`/`--local` as last play.
- **CoreELEC box catch-up**: PVR catch-up returns -32602. Always use `--m3u-url` with CoreELEC box for catch-up. `--host` for playback, `--m3u-url` only for URL building.
- **Sony TV catch-up**: Uses broadcastid from PVR. No `--m3u-url` needed.
- **Music selection**: `a`/`all`, `q`, `1`, `1,3,5`, `1-5`, `1 3 5`.
- **Local media roots**: `G:\movie`, `G:\video`, `G:\music` (Windows); `/mnt/media/{movie,video,music}/` (Linux)
- **mpv IPC**: `\\.\pipe\mpv-pipe` (Windows); `/tmp/mpv-socket` (Linux)
- **mpv instance reuse**: New cmds reuse existing mpv. Old playback continues if `q` or no results.
- **AI agent workflow**: Search with `--json` to get file paths, then `playfile`/`enqueue` to play:
- **AI agent workflow alternative**: Search with `--json` to get file paths, then `playfiles "file1" "file2" "file3" "..."` to play:
  ```
  aiplayer.py --local music 林忆莲 --json
  → 解析 JSON，取 index=4 的 file 路径
  aiplayer.py --local playfile /path/to/伤痕.flac
  aiplayer.py --local enqueue /path/to/至少还有你.flac
  ```
- **Time zones**: EPG/KODI PVR = UTC. User inputs = +8 local.
- **No plugin/virtual sources**: `plugin://`, `videodb://` rejected.
- **mpv path**: `d:\tools\mpv\mpv.exe` (Windows); `mpv` in PATH (Linux).


## AI Agent Workflow

### Two-round playfiles pattern (zero branch)

```bash
# Round 1: Search with JSON
python aiplayer/scripts/aiplayer.py --local music 林忆莲 --json
# → [{"index":1,"file":"G:/music/伤痕.flac","label":"伤痕"},...]

# Round 2: Play all files in one command (no count check needed)
python aiplayer/scripts/aiplayer.py --local playfiles "G:/music/伤痕.flac" "G:/music/至少还有你.flac"
# → "Playing 2 file(s)"
```

The `playfiles` action internally:
1. Clears current playlist
2. Appends all given paths
3. Starts playback from index 0

This eliminates the need for the AI to check "is there more than 1?" and branch between `playfile` vs `enqueue`.
