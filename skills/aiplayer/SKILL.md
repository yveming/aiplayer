---
name: aiplayer
description: >
  Control media playback using KODI (via JSON-RPC) or local mpv player.
  Defaults to local mpv playback. Pass --auto to auto-discover KODI or --host to connect directly.
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
aiplayer (entry point, installed as a uv tool)
  +-- player.py  (abstraction: PlayerMode, Player ABC, resolve helpers)
  |     +-- player_kodi.py  KodiBackend -> KodiAPI (kodi_api.py)        JSON-RPC to KODI
  |     +-- player_mpv.py   MpvBackend  -> MpvPlayer (local_player.py)  mpv IPC control
  |     +-- player_factory.py  create_player() assembles the backend
  +-- discover.py  discover KODI or detect local media dirs
  +-- search_play.py  search & play (KODI library + remote/local dirs)
  +-- pvr_epg.py  TV channels/EPG/catch-up
  +-- m3u_catchup.py  m3u parser + URL builder + XMLTV EPG
  +-- metadata.py  Douban alias/filmography expansion (optional, online)
  +-- config.py  config loader (~/.config/aiplayer/config.json, auto-generated on first run)
```

Installed as a standalone tool with `uv tool install .` and run as `aiplayer`. Update with `uv tool install . --upgrade`. Inside the project: `uv run aiplayer`.

---

## Command Format

```
aiplayer [connection-flags] <action> [query] [action-flags]
```

---

## How AI Agents Must Use This (read in order)

1. **Read the config first**: `~/.config/aiplayer/config.json`. It stores the KODI connection,
   IPTV m3u/EPG, media roots, and mpv path. This is the primary source of truth - when it is
   filled in, most commands need NO extra flags. CLI flags override config.
2. **Fill gaps once, then persist**: if `kodi.host`, `media.*`, or `iptv.m3u/epg` are empty
   when an action needs them, ask the user **once** and write the values into config.json
   (keep the JSON valid). Never ask again on later runs.
3. **Always specify the action** - there is no action inference; a bare query is an argparse
   error. `movie` = movies, `video` = episodes (SxxEyy), `music`, `tv` = live TV, `epg`,
   `catchup`, plus playback control and file actions.
4. **Connection flags**: when config `kodi.host` is set, KODI commands need NO
   `--host/--port/...` at all. Pass `--host` only to use a *different* box than config.
   Local mode is the default when config has no host and no `--host` is given.
   `--auto` (SSDP/mDNS, ~5s) only when the user explicitly asks.
5. **IPTV m3u/EPG scoping**: config `iptv.m3u` applies in local mode automatically; in KODI
   mode pass `--m3u` explicitly or PVR actions stay on KODI. When KODI returns no EPG,
   `catchup`/`epg` fall back to the m3u/XMLTV patch (config or `--m3u`/`--epg`) automatically.
6. **Playback control** (pause/skip/volume/status) works in whichever mode the *last play
   command* used - same `--host` (or none for local mode).
7. **Search with `--json`, play with `playfile`/`playfiles`**: `--json` NEVER auto-plays; it
   prints a JSON array (see "Parsing --json output"). Interactive prompts exist for humans only.

---

## Configuration File

Location: `~/.config/aiplayer/config.json` - auto-generated with defaults on first run
(any entry point: `aiplayer`, `uv run aiplayer`, `python -m aiplayer`).
First run prints `Config created: ...` - that is normal, keep going.

- **Precedence**: CLI flags > config file > built-in defaults
- **Empty value = not configured** (the tool prints a hint instead of guessing)
- `kodi.host/port/username/password/protocol`: KODI connection defaults -
  **when host is set, KODI commands need no connection flags at all**
- `media.movie/video/music`: local media root directories (**no built-in defaults**;
  local search prints a hint when empty)
- `iptv.m3u`: IPTV m3u - http(s):// URL or local file path. **Local mode only**;
  KODI mode requires explicit `--m3u`
- `iptv.epg`: XMLTV EPG fallback (priority: `--epg` > config `iptv.epg` > m3u `x-tvg-url`)
- `mpv.path`: mpv executable path (set it when `mpv` is not on PATH)
- `metadata`: online Douban expansion - `enabled` (default true), `timeout` seconds
  (default 5). Multi-language alias search + actor/director filmography fallback; fails
  silently when offline. Set `enabled: false` for fully offline use.

Typical example (local media + one KODI box + IPTV):

```json
{
  "kodi":  {"host": "192.168.100.11", "port": 9090, "username": "", "password": "", "protocol": "tcp"},
  "iptv":  {"m3u": "http://192.168.100.2:8000/iptv/iptv.m3u", "epg": ""},
  "mpv":   {"path": ""},
  "media": {"movie": ["G:\\movie"], "video": ["G:\\video"], "music": ["G:\\music"]}
}
```

With this config, `aiplayer tv "CCTV1"` talks to the KODI box, `aiplayer movie "阿凡达"`
searches local dirs, and `aiplayer catchup "CCTV1" --date yesterday --time 21:00` uses the
configured m3u - **zero connection flags**.

---

## All Actions

| Action | Description | Requires query? | Local/KODI |
|--------|-------------|-----------------|------------|
| `movie` | Search and play a movie | yes | both |
| `video` | Search and play a TV episode (S03E04) | yes | both |
| `music` | Search and play music (with `--artist`/`--album`/`--song`) | optional | both |
| `tv` | Play a live TV channel; no query = list channels | yes to play; no to list | both |
| `epg` | Browse EPG; no query = current programs of all channels (needs m3u) | optional | both |
| `catchup` | Play catch-up TV (needs `--date`/`--time`) | yes | both |
| `pause` | Toggle pause | no | both |
| `play` | Resume playback | no | both |
| `playpause` | Toggle play/pause | no | both |
| `next` | Next track/station | no | both |
| `prev` | Previous track/station | no | both |
| `stop` | Stop playback and exit local mpv (respawns on next play) | no | both |
| `restart` | Restart current track | no | both |
| `volume_up` | Volume +10% | no | both |
| `volume_down` | Volume -10% | no | both |
| `mute` | Toggle mute | no | both |
| `status` | Show current playback info | no | both |
| `playfile` | Play/replace a file by path | yes (path) | both |
| `enqueue` | Append a file to playlist | yes (path) | both |
| `playfiles` | Clear playlist, play multiple files by path | yes (paths...) | both |

---

## All Command-Line Flags

| Flag | Type | Used with | Description |
|------|------|-----------|-------------|
| `--host` | IP | KODI mode | KODI IP (omit when config kodi.host is set) |
| `--port` | int | `--host` | KODI port (default 9090 or 8080) |
| `--protocol` | tcp/http/auto | `--host` | Connection protocol |
| `--username` | str | `--host` http | HTTP auth username |
| `--password` | str | `--host` http | HTTP auth password |
| `--auto` | flag | standalone | Auto-discover KODI (SSDP/mDNS, ~5s), fall back to local mpv |
| `--m3u` | URL or path | tv/catchup/epg | IPTV m3u (config iptv.m3u = local mode only; KODI mode needs it explicitly) |
| `--epg` | URL or path | epg/catchup | XMLTV EPG (priority: --epg > config iptv.epg > m3u x-tvg-url) |
| `--artist` | str | music | Artist name filter |
| `--album` | str | music | Album name filter |
| `--song` | str | music | Song name filter |
| `--shuffle` | flag | music | Random playback order |
| `--date` | str | catchup, epg | Date keyword or YYYY-MM-DD |
| `--time` | str | catchup, epg | Time keyword or HH:MM |
| `--json` | flag | search actions | JSON array output, never auto-plays (for AI) |
| `--debug` | flag | any | Verbose debug output |
| `--mpv-path` | path | local mode | mpv executable path |
| `--max-depth` | int | search | Directory recursion depth |

---

## Action Reference

Examples assume the config from the Configuration File section is filled in
(kodi.host + media roots + iptv.m3u). Override forms are shown for one-off
overrides only.

### movie — Search and play movies

```
# config-driven (recommended)
aiplayer movie "阿凡达"
aiplayer movie "Avatar" --json

# temporary override (different box than config)
aiplayer --host 192.168.100.11 --port 9090 --protocol http --username kodi --password hermes movie "Interstellar"
```

Keywords: `放电影`, `电影`, `movie`

### video — Search and play TV episodes

Query must contain season/episode info (S03E04, 3x04, 第N季第M集).
Chinese queries find English-named files and vice versa via Douban alias
expansion (see Important Notes).

```
# config-driven
aiplayer video "黑暗物质第三季第四集"
aiplayer video "Dark Matter S03E04" --json

# temporary override
aiplayer --host 192.168.100.11 --port 9090 video "Dark Matter S03E04"
```

Keywords: `放视频`, `剧集`, `视频`, `连续`, `video`, `episode`

### music — Search and play music

Uses `--artist`, `--album`, `--song` flags (all optional). `--shuffle` for random.

```
# config-driven
aiplayer music --artist "赵传"
aiplayer music --artist "赵传" --album "我是一只小小鸟" --song "我是一只小小鸟" --shuffle
aiplayer music "我是一只小小鸟" --json
```

Interactive selection (`1`, `1,3,5`, `1-5`, `a`/`all`, `q`) is for humans only -
AI agents use `--json` + `playfiles` instead (see Parsing --json output).

Keywords: `放音乐`, `音乐`, `music`, `song`

### tv — Live TV (play / list channels)

```
# play a channel (KODI PVR when kodi.host is set; m3u stream in local mode)
aiplayer tv "CCTV1"
aiplayer tv "湖南卫视"

# list channels (no query)
aiplayer tv

# temporary override: use a different m3u
aiplayer tv "CCTV1" --m3u http://192.168.100.2:8000/iptv/iptv.m3u
```

In KODI mode without `--m3u`, PVR is used. In local mode, config `iptv.m3u` is used.

Keywords: `放电视`, `直播`, `live`, `tv`, `频道`

### epg — Browse EPG

With a channel: EPG around now, or for `--date`/`--time`. Without a query:
the current program of every channel (requires `--m3u` or config `iptv.m3u`).

```
# config-driven
aiplayer epg "CCTV1"
aiplayer epg "CCTV1" --date today
aiplayer epg "CCTV1" --date yesterday
aiplayer epg                              # all channels' current programs

# temporary override
aiplayer epg "CCTV1" --m3u http://192.168.100.2:8000/iptv/iptv.m3u --date yesterday
```

Keywords: `节目单`, `epg`, `节目表`

### catchup — TV catch-up / 回看

Requires `--date` and `--time`. Date keywords: yesterday/today/tomorrow/昨天/前天/明天/后天. Time: HH:MM or Chinese like 9点30分/十点半.

```
# config-driven (m3u/epg from config; local mode)
aiplayer catchup "CCTV1" --date yesterday --time 21:00

# KODI Sony box (broadcastid; config m3u is ignored in KODI mode)
aiplayer --host 192.168.100.43 --port 8080 --protocol http --username kodi --password hermes catchup "CCTV1" --date yesterday --time "晚上9点"

# KODI box without catch-up support: pass --m3u explicitly (or the config
# m3u/epg patch kicks in automatically when KODI returns no EPG)
aiplayer --host 192.168.100.11 --port 9090 catchup "CCTV1" --date yesterday --time 21:00 --m3u http://192.168.100.2:8000/iptv/iptv.m3u
```

Keywords: `回看`, `电视回看`, `catchup`

### Playback control

Same connection flags as the last play command (config kodi.host -> no flags for KODI).

```
aiplayer pause / play / playpause / next / prev / stop / restart
aiplayer volume_up / volume_down / mute
aiplayer status
```

Keywords: `暂停`(pause), `继续`/`播放`(play), `下一首`/`下一集`(next), `上一首`/`上一集`(prev), `重播`/`从头开始`(restart), `停止`(stop), `大声点`(volume_up), `小声点`(volume_down), `静音`(mute), `当前播放`/`状态`(status)

---

## Parsing --json output (for AI)

Search actions (`movie`/`video`/`music` with `--json`) print a JSON array and never play.
Field shapes:

```jsonc
// KODI library matches (movie)
[{"index": 1, "file": "...", "label": "Title", "year": 2009}]

// KODI TV library matches (video)
[{"index": 1, "file": "...", "label": "Show - S03E04: Title", "showtitle": "Show", "season": 3, "episode": 4}]

// directory matches (local dirs / KODI file sources)
[{"index": 1, "file": "...", "label": "basename", "display": "a / b / c", "type": "file|directory", "source": "root"}]

// music
[{"index": 1, "file": "...", "label": "Song", "artist": "...", "album": "..."}]
```

Exit codes: `0` = success (played, or JSON emitted), `1` = no match / runtime failure,
`2` = command-line error (bad action or arguments).

Two-round playfiles pattern (no branching needed):

```bash
# Round 1: search
aiplayer music 我是一只小小鸟 --json
# -> [{"index":1,"file":"G:/music/我恨.flac","label":"我恨"},...]

# Round 2: play everything found in one command
aiplayer playfiles "G:/music/我恨.flac" "G:/music/另一首.flac"
# -> "Playing 2 file(s)"
```

`playfiles` clears the playlist, appends all paths, and starts at index 0 - so there is
no need to branch between `playfile` and `enqueue`.

---

## Ask user for missing config (once, then persist)

If `kodi.host`, `media.*`, or `iptv.m3u/epg` are missing when an action needs them, ask the
user once and write the values into `~/.config/aiplayer/config.json` (keep the JSON valid)
instead of asking again on later runs. Example IPTV backend:
http://192.168.100.2:8000/iptv/iptv.m3u

---

## Important Notes

- **Discovery is slow (~5s)**: never `--auto` unless the user asks; prefer config `kodi.host` or `--host`.
- **CoreELEC/11-box catch-up**: PVR catch-up returns -32602. Either pass `--m3u` explicitly, or let the automatic m3u/XMLTV patch use config `iptv.m3u`/`iptv.epg`.
- **Sony TV catch-up**: broadcastid from PVR works; config m3u is ignored in KODI mode, so catchup stays on broadcastid.
- **m3u scoping**: config `iptv.m3u` applies in local mode only; in KODI mode pass `--m3u` explicitly (PVR actions are never hijacked). When KODI returns no EPG, `catchup`/`epg` fall back to the m3u/XMLTV patch automatically (config or `--m3u`/`--epg`).
- **Catchup time filling**: catchup placeholders (incl. `{utc:}`-named ones) are filled with box-local wall clock - mirrors KODI pvr.iptvsimple's actual behaviour (field-verified: the backend interprets playseek as local time).
- **Local media roots**: from config "media" section (no built-in defaults).
- **Online metadata (Douban)**: when a movie/video search finds nothing, Douban expands the query into alias titles (zh<->en) and retries; person names fall back to filmography. Unofficial endpoints - failures degrade silently to local-only search. Music search never goes online.
- **mpv IPC**: `\\.\pipe\mpv-pipe` (Windows); `/tmp/mpv-socket` (Linux). New commands reuse a running mpv; `stop` exits the process (next play starts a fresh one). Old playback continues if the search ends with `q` or no results.
- **Time zones**: EPG/KODI PVR = UTC. User inputs = +8 local.
- **No plugin/virtual sources**: `plugin://`, `videodb://` rejected.
- **mpv not found**: install mpv (Windows: `winget install mpv-player.mpv-CI.MSVC`) or set `mpv.path` in config.